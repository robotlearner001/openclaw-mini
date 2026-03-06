from __future__ import annotations

import atexit
import asyncio
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings


class CodexClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session_store_path = settings.codex_session_store_path
        self._session_store: dict[str, dict[str, object]] = self._load_session_store()
        atexit.register(self._archive_all_sessions_on_exit)

    def _load_session_store(self) -> dict[str, dict[str, object]]:
        path = self._session_store_path
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        parsed: dict[str, dict[str, object]] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            parsed[key] = value
        return parsed

    def _save_session_store(self) -> None:
        self._session_store_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_store_path.write_text(
            json.dumps(self._session_store, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _is_record_fresh(self, record: dict[str, object]) -> bool:
        last_active_at = record.get("last_active_at")
        if not isinstance(last_active_at, (int, float)):
            return False
        return time.time() - float(last_active_at) <= float(self._settings.codex_session_ttl_sec)

    def _safe_slug(self, text: str) -> str:
        chars = [c.lower() if c.isalnum() else "-" for c in text]
        slug = "".join(chars)
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug.strip("-")[:60] or "session"

    def _memory_file_path(self, conversation_key: str, ended_at: datetime) -> Path:
        stamp = ended_at.strftime("%Y-%m-%d_%H%M%S")
        key_slug = self._safe_slug(conversation_key)
        filename = f"{stamp}_{key_slug}.md"
        return self._settings.codex_memory_dir / filename

    def _archive_session(self, conversation_key: str, record: dict[str, object], reason: str) -> None:
        turns = record.get("turns")
        if not isinstance(turns, list) or not turns:
            return

        started_at = record.get("started_at_iso")
        ended_at = datetime.now(timezone.utc)
        memory_path = self._memory_file_path(conversation_key, ended_at)
        memory_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# Mini OpenClaw Session Memory",
            "",
            f"- conversation_key: {conversation_key}",
            f"- archived_at_utc: {ended_at.isoformat()}",
            f"- archive_reason: {reason}",
        ]
        if isinstance(started_at, str) and started_at:
            lines.append(f"- session_started_at_utc: {started_at}")

        thread_id = record.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            lines.append(f"- codex_thread_id: {thread_id}")

        lines.extend(["", "## Transcript", ""])

        for turn in turns:
            if not isinstance(turn, dict):
                continue
            role = turn.get("role")
            text = turn.get("text")
            at = turn.get("at")
            if not isinstance(role, str) or not isinstance(text, str):
                continue
            timestamp = at if isinstance(at, str) and at else "unknown-time"
            lines.append(f"### {role} ({timestamp})")
            lines.append("")
            lines.append(text.strip())
            lines.append("")

        memory_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def _archive_if_stale(self, conversation_key: str) -> None:
        record = self._session_store.get(conversation_key)
        if not isinstance(record, dict):
            return
        if self._is_record_fresh(record):
            return
        self._archive_session(conversation_key, record, reason="ttl_expired")
        self._session_store.pop(conversation_key, None)
        self._save_session_store()

    def _archive_all_sessions_on_exit(self) -> None:
        changed = False
        for conversation_key, record in list(self._session_store.items()):
            if not isinstance(record, dict):
                continue
            self._archive_session(conversation_key, record, reason="process_exit")
            self._session_store.pop(conversation_key, None)
            changed = True
        if changed:
            self._save_session_store()

    def _resolve_active_thread_id(self, conversation_key: str) -> str | None:
        self._archive_if_stale(conversation_key)
        record = self._session_store.get(conversation_key)
        if not isinstance(record, dict):
            return None
        thread_id = record.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            return None
        return thread_id

    def _record_turn_pair(
        self,
        conversation_key: str,
        thread_id: str | None,
        user_text: str,
        assistant_text: str,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        now_epoch = time.time()

        record = self._session_store.get(conversation_key)
        if not isinstance(record, dict):
            record = {}

        if not isinstance(record.get("started_at_iso"), str):
            record["started_at_iso"] = now_iso

        if isinstance(thread_id, str) and thread_id:
            record["thread_id"] = thread_id

        turns = record.get("turns")
        if not isinstance(turns, list):
            turns = []

        turns.append({"at": now_iso, "role": "user", "text": user_text})
        turns.append({"at": now_iso, "role": "assistant", "text": assistant_text})

        max_turns = self._settings.codex_session_max_turns
        if len(turns) > max_turns:
            turns = turns[-max_turns:]

        record["turns"] = turns
        record["last_active_at"] = now_epoch

        self._session_store[conversation_key] = record
        self._save_session_store()

    @staticmethod
    def _extract_thread_id(stdout_text: str) -> str | None:
        for line in stdout_text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "thread.started" and isinstance(payload.get("thread_id"), str):
                return payload["thread_id"]
        return None

    def _build_codex_cmd_prefix(self) -> list[str]:
        cmd = [self._settings.codex_command]
        if self._settings.codex_dangerous_bypass:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
            return cmd
        if self._settings.codex_sandbox:
            cmd.extend(["--sandbox", self._settings.codex_sandbox])
        if self._settings.codex_ask_for_approval:
            cmd.extend(["--ask-for-approval", self._settings.codex_ask_for_approval])
        return cmd

    async def generate_reply(
        self,
        conversation_key: str,
        soul: str,
        skills_context: str,
        user_text: str,
    ) -> str:
        memory_dir = self._settings.codex_memory_dir
        memory_hint = (
            "MEMORY POLICY:\n"
            f"- Session memory files are stored in: {memory_dir}\n"
            "- If the user message is unclear, references prior talks, or needs extra context, search this memory folder first.\n"
            "- Use memory facts only when relevant to the current message; do not invent missing context."
        )

        instructions = (
            "You are Mini OpenClaw, a Discord assistant. Follow the SOUL.md guidance exactly.\n\n"
            f"SOUL.md:\n{soul}\n\n"
            f"SKILLS:\n{skills_context}\n\n"
            f"{memory_hint}\n\n"
            f"USER MESSAGE:\n{user_text}"
        )

        with tempfile.NamedTemporaryFile(prefix="codex-last-", suffix=".txt", delete=False) as f:
            output_file = Path(f.name)

        thread_id = self._resolve_active_thread_id(conversation_key)
        if thread_id:
            # Reuse session if it is still fresh.
            cmd = self._build_codex_cmd_prefix()
            if self._settings.codex_enable_search:
                cmd.append("--search")
            if self._settings.codex_use_full_auto and not (
                self._settings.codex_dangerous_bypass
                or self._settings.codex_sandbox
                or self._settings.codex_ask_for_approval
            ):
                cmd.append("--full-auto")
            cmd.extend(
                [
                    "exec",
                    "resume",
                    thread_id,
                    "--json",
                ],
            )
            if self._settings.codex_model:
                cmd.extend(["--model", self._settings.codex_model])
            cmd.extend(["--output-last-message", str(output_file)])
            cmd.append(instructions)
        else:
            cmd = self._build_codex_cmd_prefix()
            if self._settings.codex_use_full_auto and not (
                self._settings.codex_dangerous_bypass
                or self._settings.codex_sandbox
                or self._settings.codex_ask_for_approval
            ):
                cmd.append("--full-auto")
            if self._settings.codex_enable_search:
                cmd.append("--search")
            cmd.extend(self._settings.codex_base_args)
            cmd.append("--json")
            if self._settings.codex_model:
                cmd.extend(["--model", self._settings.codex_model])
            cmd.extend(["--output-last-message", str(output_file)])
            cmd.append(instructions)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self._settings.codex_workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=float(self._settings.codex_timeout_sec),
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                timed_out_text = f"Codex timed out after {self._settings.codex_timeout_sec}s."
                self._record_turn_pair(conversation_key, thread_id, user_text, timed_out_text)
                return timed_out_text

            stdout_text = (stdout or b"").decode("utf-8", errors="replace").strip()
            discovered_thread_id = self._extract_thread_id(stdout_text)
            active_thread_id = discovered_thread_id or thread_id

            file_text = ""
            if output_file.exists():
                file_text = output_file.read_text(encoding="utf-8", errors="replace").strip()
            if file_text:
                self._record_turn_pair(conversation_key, active_thread_id, user_text, file_text)
                return file_text

            if proc.returncode != 0:
                failure_text = f"Codex CLI failed (exit {proc.returncode}).\n{stdout_text[:3000]}"
                self._record_turn_pair(conversation_key, active_thread_id, user_text, failure_text)
                return failure_text

            fallback_text = stdout_text[:3000] or "Codex returned no output."
            self._record_turn_pair(conversation_key, active_thread_id, user_text, fallback_text)
            return fallback_text
        finally:
            output_file.unlink(missing_ok=True)
