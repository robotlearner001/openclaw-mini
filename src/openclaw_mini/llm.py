from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path

from .config import Settings


class CodexClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session_store_path = settings.codex_session_store_path
        self._session_store: dict[str, dict[str, object]] = self._load_session_store()

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

    def _resolve_active_thread_id(self, conversation_key: str) -> str | None:
        record = self._session_store.get(conversation_key)
        if not isinstance(record, dict):
            return None
        thread_id = record.get("thread_id")
        last_active_at = record.get("last_active_at")
        if not isinstance(thread_id, str) or not thread_id:
            return None
        if not isinstance(last_active_at, (int, float)):
            return None
        if time.time() - float(last_active_at) > float(self._settings.codex_session_ttl_sec):
            return None
        return thread_id

    def _update_thread_record(self, conversation_key: str, thread_id: str) -> None:
        self._session_store[conversation_key] = {
            "thread_id": thread_id,
            "last_active_at": time.time(),
        }
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
        instructions = (
            "You are Mini OpenClaw, a Discord assistant. Follow the SOUL.md guidance exactly.\n\n"
            f"SOUL.md:\n{soul}\n\n"
            f"SKILLS:\n{skills_context}\n\n"
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
                return f"Codex timed out after {self._settings.codex_timeout_sec}s."

            stdout_text = (stdout or b"").decode("utf-8", errors="replace").strip()
            discovered_thread_id = self._extract_thread_id(stdout_text)
            if discovered_thread_id:
                self._update_thread_record(conversation_key, discovered_thread_id)
            elif thread_id:
                # Keep session alive on successful resume even if no event was emitted.
                self._update_thread_record(conversation_key, thread_id)

            file_text = ""
            if output_file.exists():
                file_text = output_file.read_text(encoding="utf-8", errors="replace").strip()
            if file_text:
                return file_text

            if proc.returncode != 0:
                return f"Codex CLI failed (exit {proc.returncode}).\n{stdout_text[:3000]}"
            return stdout_text[:3000] or "Codex returned no output."
        finally:
            output_file.unlink(missing_ok=True)
