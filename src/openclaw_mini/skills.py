from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillResult:
    handled: bool
    response: str | None = None


HELP_TEXT = """Commands:
- /help   Show this help
- /ping   Health check
- /skills Show available skills
- /soul   Show current soul summary

Anything else is sent to local Codex CLI."""


def load_skill_cards(skills_dir: Path | None = None) -> list[tuple[str, str]]:
    base_dir = skills_dir or Path("skills")
    if not base_dir.exists():
        return []

    cards: list[tuple[str, str]] = []
    for path in sorted(base_dir.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not content:
            continue
        cards.append((path.stem, content))
    return cards


def format_skill_cards_for_prompt(cards: list[tuple[str, str]]) -> str:
    if not cards:
        return "No external skill cards loaded."
    lines = []
    for name, content in cards:
        lines.append(f"[{name}]")
        lines.append(content[:1200])
    return "\n\n".join(lines)


def handle_skill_command(
    message: str,
    soul_excerpt: str,
    skill_cards: list[tuple[str, str]],
) -> SkillResult:
    text = message.strip()
    if not text.startswith("/"):
        return SkillResult(handled=False)

    lower = text.lower()
    if lower.startswith("/help"):
        return SkillResult(handled=True, response=HELP_TEXT)
    if lower.startswith("/ping"):
        return SkillResult(handled=True, response="pong")
    if lower.startswith("/skills"):
        external = ", ".join(name for name, _ in skill_cards) or "(none)"
        return SkillResult(
            handled=True,
            response=(
                "Built-in skills: help, ping, skills, soul\n"
                f"Skill cards from ./skills: {external}"
            ),
        )
    if lower.startswith("/soul"):
        return SkillResult(handled=True, response=f"Soul:\n{soul_excerpt}")

    return SkillResult(
        handled=True,
        response="Unknown command. Try /help",
    )
