from __future__ import annotations

from pathlib import Path

DEFAULT_SOUL = """# SOUL.md - Default Soul\n\nBe helpful, concise, and accurate.\n"""


def load_soul(soul_path: Path) -> str:
    if soul_path.exists():
        return soul_path.read_text(encoding="utf-8").strip()
    return DEFAULT_SOUL
