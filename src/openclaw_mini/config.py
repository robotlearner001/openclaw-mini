from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    discord_bot_token: str
    soul_path: Path
    allowed_channel_ids: frozenset[int]
    openai_enable_web_search: bool


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


def load_settings() -> Settings:
    load_dotenv()

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    discord_bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()

    if not openai_api_key:
        raise ValueError("Missing OPENAI_API_KEY")
    if not discord_bot_token:
        raise ValueError("Missing DISCORD_BOT_TOKEN")

    return Settings(
        openai_api_key=openai_api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.3-codex").strip() or "gpt-5.3-codex",
        discord_bot_token=discord_bot_token,
        soul_path=Path(os.getenv("SOUL_PATH", "SOUL.md")).expanduser(),
        allowed_channel_ids=_parse_channel_ids(os.getenv("DISCORD_ALLOWED_CHANNEL_IDS")),
        openai_enable_web_search=_parse_bool(os.getenv("OPENAI_ENABLE_WEB_SEARCH"), True),
    )
