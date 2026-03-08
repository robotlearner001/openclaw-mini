from __future__ import annotations

import logging

import discord

from .config import Settings
from .llm import CodexClient
from .skills import format_skill_cards_for_prompt, handle_skill_command, load_skill_cards
from .soul import load_soul

logger = logging.getLogger(__name__)
DISCORD_MESSAGE_SAFE_LIMIT = 1900


def _chunk_text(text: str, max_len: int = DISCORD_MESSAGE_SAFE_LIMIT) -> list[str]:
    if len(text) <= max_len:
        return [text]

    remaining = text
    chunks: list[str] = []
    while len(remaining) > max_len:
        split_at = remaining.rfind("\n", 0, max_len + 1)
        if split_at < max_len // 2:
            split_at = remaining.rfind(" ", 0, max_len + 1)
        if split_at < max_len // 2:
            split_at = max_len

        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:max_len]
            split_at = max_len
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)
    return chunks


async def _reply_in_chunks(message: discord.Message, text: str) -> None:
    content = text or ""
    for chunk in _chunk_text(content):
        await message.reply(chunk, mention_author=False)


def build_discord_client(settings: Settings) -> discord.Client:
    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)
    codex = CodexClient(settings)
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
            await _reply_in_chunks(message, skill_result.response or "")
            return

        async with message.channel.typing():
            try:
                conversation_key = (
                    f"guild:{message.guild.id}:channel:{message.channel.id}"
                    if message.guild is not None
                    else f"dm:{message.channel.id}"
                )
                result = await codex.generate_reply(
                    conversation_key=conversation_key,
                    soul=soul,
                    skills_context=skills_context,
                    user_text=text,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Codex local request failed")
                await _reply_in_chunks(message, f"Codex local request failed: {exc}")
                return

        await _reply_in_chunks(message, result)

    return client
