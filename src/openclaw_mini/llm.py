from __future__ import annotations

from openai import OpenAI


class CodexClient:
    def __init__(self, api_key: str, model: str, enable_web_search: bool = True) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._enable_web_search = enable_web_search

    def generate_reply(self, soul: str, skills_context: str, user_text: str) -> str:
        instructions = (
            "You are Mini OpenClaw, a Discord assistant. Follow the SOUL.md guidance exactly.\n\n"
            f"SOUL.md:\n{soul}\n\n"
            f"SKILLS:\n{skills_context}"
        )
        kwargs: dict = {
            "model": self._model,
            "instructions": instructions,
            "input": user_text,
        }
        if self._enable_web_search:
            kwargs["tools"] = [{"type": "web_search_preview"}]

        response = self._client.responses.create(**kwargs)
        return (response.output_text or "").strip() or "I could not generate a response."
