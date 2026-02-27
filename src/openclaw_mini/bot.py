from __future__ import annotations

import logging

import discord

from .config import Settings
from .llm import CodexClient
from .skills import format_skill_cards_for_prompt, handle_skill_command, load_skill_cards
from .soul import load_soul

logger = logging.getLogger(__name__)


def build_discord_client(settings: Settings) -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)
    codex = CodexClient(
        settings.openai_api_key,
        settings.openai_model,
        enable_web_search=settings.openai_enable_web_search,
    )
    skill_cards = load_skill_cards()
    skills_context = format_skill_cards_for_prompt(skill_cards)

    @client.event
    async def on_ready() -> None:
        logger.info("Connected as %s", client.user)

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return

        if settings.allowed_channel_ids and message.channel.id not in settings.allowed_channel_ids:
            return

        text = message.content.strip()
        if not text:
            return

        soul = load_soul(settings.soul_path)
        soul_excerpt = soul[:1200]

        skill_result = handle_skill_command(text, soul_excerpt, skill_cards)
        if skill_result.handled:
            await message.reply(skill_result.response or "")
            return

        async with message.channel.typing():
            try:
                result = codex.generate_reply(
                    soul=soul,
                    skills_context=skills_context,
                    user_text=text,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("OpenAI request failed")
                await message.reply(f"OpenAI request failed: {exc}")
                return

        await message.reply(result)

    return client
