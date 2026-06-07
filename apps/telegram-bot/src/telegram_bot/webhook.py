"""Обработка входящего Telegram-update: нормализация -> brain-api -> действия."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from telegram_bot.brain_client import BrainClient
from telegram_bot.client import TelegramClient
from telegram_bot.commands import is_command
from telegram_bot.handlers import (
    build_callback_event,
    build_command_event,
    build_message_event,
)
from telegram_bot.renderer import execute_actions

logger = logging.getLogger(__name__)

# ASR service endpoint (internal docker network)
_ASR_URL = "http://asr-service:8030/transcribe"


async def process_update(
    update: dict[str, Any],
    client: TelegramClient,
    brain: BrainClient,
) -> None:
    """Route update: my_chat_member / callback / voice / command / message."""

    # ── Bot added to group → auto /start ─────────────────────────────────
    if "my_chat_member" in update:
        await _handle_bot_joined(update, client, brain)
        return

    # ── Inline button callbacks ───────────────────────────────────────────
    if "callback_query" in update:
        event = build_callback_event(update, update["callback_query"])
        actions = await brain.send_callback_event(event)
        await execute_actions(client, actions.actions)
        return

    message = (
        update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
        or update.get("edited_channel_post")
    )
    if not message:
        logger.debug("Update без message/callback_query пропущен")
        return

    # ── Voice / audio messages → ASR → treat as text ─────────────────────
    voice = message.get("voice") or message.get("audio")
    if voice and not message.get("text"):
        await _handle_voice(update, message, voice, client, brain)
        return

    text = message.get("text", "")
    if not text:
        return

    # ── Commands ──────────────────────────────────────────────────────────
    if is_command(text):
        command_event = build_command_event(update, message)
        if command_event.command == "start" and _link_code(command_event.args):
            sender = command_event.sender
            actions = await brain.send_telegram_link(
                code=_link_code(command_event.args) or "",
                tg_user_id=sender.id,
                chat_id=command_event.chat.id,
                username=sender.username,
                first_name=sender.first_name,
                last_name=sender.last_name,
            )
        else:
            actions = await brain.send_command_event(command_event)
    else:
        message_event = build_message_event(update, message)
        actions = await brain.send_message_event(message_event)

    await execute_actions(client, actions.actions)


def _link_code(args: list[str]) -> str | None:
    if not args:
        return None
    value = args[0].strip()
    if not value.startswith("link_"):
        return None
    code = value.removeprefix("link_").strip()
    return code or None


async def _handle_bot_joined(
    update: dict[str, Any],
    client: TelegramClient,
    brain: BrainClient,
) -> None:
    """When bot is added to a group chat — auto-trigger /start."""
    member_update = update["my_chat_member"]
    new_status = member_update.get("new_chat_member", {}).get("status", "")
    chat = member_update.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type", "group")

    if new_status not in ("member", "administrator") or not chat_id:
        return

    logger.info("Bot joined chat %s (%s), triggering /start", chat_id, chat_type)

    # Build a synthetic /start command event
    from datetime import UTC, datetime

    from grey_cardinal_contracts import TelegramChatInfo, TelegramCommandEvent, TelegramSender

    event = TelegramCommandEvent(
        update_id=update.get("update_id", 0),
        message_id=0,
        chat=TelegramChatInfo(
            id=chat_id,
            type=chat_type,
            title=chat.get("title"),
        ),
        sender=TelegramSender(
            id=member_update.get("from", {}).get("id", 0),
            username=member_update.get("from", {}).get("username"),
            first_name=member_update.get("from", {}).get("first_name"),
        ),
        command="start",
        args=[],
        text="/start",
        date=datetime.now(UTC),
        raw=update,
    )
    actions = await brain.send_command_event(event)
    await execute_actions(client, actions.actions)


async def _handle_voice(
    update: dict[str, Any],
    message: dict[str, Any],
    voice: dict[str, Any],
    client: TelegramClient,
    brain: BrainClient,
) -> None:
    """Download voice message and transcribe via ASR, then process as text."""
    chat_id = message.get("chat", {}).get("id", 0)
    file_id = voice.get("file_id", "")
    duration = voice.get("duration", 0)

    if not file_id:
        return

    logger.info("Voice message received (duration=%ss) from chat %s", duration, chat_id)

    # Get file path from Telegram
    file_info = await client.get_file(file_id)
    if not file_info:
        logger.warning("Could not get file info for voice %s", file_id)
        return

    file_path = file_info.get("file_path", "")
    if not file_path:
        return

    # Download file bytes
    audio_bytes = await client.download_file(file_path)
    if not audio_bytes:
        logger.warning("Could not download voice file %s", file_path)
        return

    # Transcribe via ASR service
    transcript = await _transcribe(audio_bytes, file_path)
    if not transcript:
        logger.info("ASR returned empty transcript for voice in chat %s", chat_id)
        return

    logger.info("Voice transcribed (%d chars): %s...", len(transcript), transcript[:60])

    # Inject transcript as a regular message event
    synthetic_message = {
        **message,
        "text": f"🎙 [голосовое] {transcript}",
    }
    msg_event = build_message_event(update, synthetic_message)
    actions = await brain.send_message_event(msg_event)
    await execute_actions(client, actions.actions)


async def _transcribe(audio_bytes: bytes, file_path: str) -> str:
    """Send raw audio bytes to ASR service and return transcript text.

    asr-service reads ``request.body()`` and requires ``Content-Type: audio/*``
    (it rejects multipart with 415). Telegram voice is OGG/Opus, which
    faster-whisper decodes via ffmpeg regardless of the declared subtype.
    The call is internal (http://asr-service) so we bypass the Telegram proxy.
    """
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "ogg"
    content_type = {
        "oga": "audio/ogg",
        "ogg": "audio/ogg",
        "opus": "audio/ogg",
        "mp3": "audio/mpeg",
        "m4a": "audio/mp4",
        "wav": "audio/wav",
    }.get(ext, "audio/ogg")

    try:
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            resp = await client.post(
                _ASR_URL,
                content=audio_bytes,
                headers={"Content-Type": content_type},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("text", "").strip()
            logger.warning("ASR service returned %s: %s", resp.status_code, resp.text[:200])
    except httpx.HTTPError as exc:
        logger.error("ASR transcription failed: %s", exc)
    return ""
