from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    soul_path: Path
    allowed_channel_ids: frozenset[int]
    codex_command: str
    codex_base_args: tuple[str, ...]
    codex_model: str | None
    codex_timeout_sec: int
    codex_workspace_root: Path
    codex_enable_search: bool
    codex_use_full_auto: bool
    codex_session_ttl_sec: int
    codex_session_store_path: Path
    codex_sandbox: str | None
    codex_ask_for_approval: str | None
    codex_dangerous_bypass: bool


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {raw}")


def _parse_channel_ids(raw: str | None) -> frozenset[int]:
    if not raw:
        return frozenset()
    values: list[int] = []
    for chunk in raw.split(","):
        stripped = chunk.strip()
        if not stripped:
            continue
        try:
            values.append(int(stripped))
        except ValueError as exc:
            raise ValueError(f"Invalid channel ID in DISCORD_ALLOWED_CHANNEL_IDS: {stripped}") from exc
    return frozenset(values)


def _parse_positive_int(raw: str | None, default: int, env_name: str) -> int:
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid integer in {env_name}: {raw}") from exc
    if value <= 0:
        raise ValueError(f"{env_name} must be > 0")
    return value


def _parse_one_of(raw: str | None, allowed: frozenset[str], env_name: str) -> str | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if not value:
        return None
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"Invalid value in {env_name}: {raw}. Allowed: {allowed_values}")
    return value


def load_settings() -> Settings:
    load_dotenv()

    discord_bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not discord_bot_token:
        raise ValueError("Missing DISCORD_BOT_TOKEN")
    codex_command = os.getenv("CODEX_COMMAND", "codex").strip() or "codex"
    codex_base_args_raw = (
        os.getenv("CODEX_BASE_ARGS", "exec --skip-git-repo-check").strip()
        or "exec --skip-git-repo-check"
    )
    codex_base_args = tuple(shlex.split(codex_base_args_raw))
    if not codex_base_args:
        raise ValueError("CODEX_BASE_ARGS cannot be empty")
    if codex_base_args[0] != "exec":
        raise ValueError("CODEX_BASE_ARGS must start with 'exec'")
    if "--seach" in codex_base_args:
        raise ValueError("CODEX_BASE_ARGS contains '--seach' typo. Did you mean '--search'?")
    if "--search" in codex_base_args:
        codex_base_args = tuple(arg for arg in codex_base_args if arg != "--search")

    if shutil.which(codex_command) is None:
        raise ValueError(f"Codex command not found in PATH: {codex_command}")

    codex_workspace_root = Path(os.getenv("CODEX_WORKSPACE_ROOT", ".")).expanduser()
    if not codex_workspace_root.is_dir():
        raise ValueError(
            f"CODEX_WORKSPACE_ROOT does not exist or is not a directory: {codex_workspace_root}"
        )

    codex_model = os.getenv("CODEX_MODEL", "").strip() or None
    codex_sandbox = _parse_one_of(
        os.getenv("CODEX_SANDBOX"),
        frozenset({"read-only", "workspace-write", "danger-full-access"}),
        "CODEX_SANDBOX",
    )
    codex_ask_for_approval = _parse_one_of(
        os.getenv("CODEX_ASK_FOR_APPROVAL"),
        frozenset({"untrusted", "on-failure", "on-request", "never"}),
        "CODEX_ASK_FOR_APPROVAL",
    )
    codex_dangerous_bypass = _parse_bool(os.getenv("CODEX_DANGEROUS_BYPASS"), False)

    return Settings(
        discord_bot_token=discord_bot_token,
        soul_path=Path(os.getenv("SOUL_PATH", "SOUL.md")).expanduser(),
        allowed_channel_ids=_parse_channel_ids(os.getenv("DISCORD_ALLOWED_CHANNEL_IDS")),
        codex_command=codex_command,
        codex_base_args=codex_base_args,
        codex_model=codex_model,
        codex_timeout_sec=_parse_positive_int(os.getenv("CODEX_TIMEOUT_SEC"), 240, "CODEX_TIMEOUT_SEC"),
        codex_workspace_root=codex_workspace_root,
        codex_enable_search=_parse_bool(os.getenv("CODEX_ENABLE_SEARCH"), True),
        codex_use_full_auto=_parse_bool(os.getenv("CODEX_USE_FULL_AUTO"), True),
        codex_session_ttl_sec=_parse_positive_int(
            os.getenv("CODEX_SESSION_TTL_SEC"),
            3600,
            "CODEX_SESSION_TTL_SEC",
        ),
        codex_session_store_path=Path(
            os.getenv("CODEX_SESSION_STORE_PATH", ".codex-discord-sessions.json"),
        ).expanduser(),
        codex_sandbox=codex_sandbox,
        codex_ask_for_approval=codex_ask_for_approval,
        codex_dangerous_bypass=codex_dangerous_bypass,
    )
