"""Обработка входящего Telegram-update: нормализация -> brain-api -> действия."""

from __future__ import annotations

import logging
from typing import Any

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


async def process_update(
    update: dict[str, Any],
    client: TelegramClient,
    brain: BrainClient,
) -> None:
    """Маршрутизировать update: callback / command / message."""
    if "callback_query" in update:
        event = build_callback_event(update, update["callback_query"])
        actions = await brain.send_callback_event(event)
        await execute_actions(client, actions.actions)
        return

    message = update.get("message") or update.get("edited_message")
    if not message:
        logger.debug("Update без message/callback_query пропущен")
        return

    text = message.get("text", "")
    if is_command(text):
        command_event = build_command_event(update, message)
        actions = await brain.send_command_event(command_event)
    else:
        if not text:
            return  # на P0 обрабатываем только текстовые сообщения
        message_event = build_message_event(update, message)
        actions = await brain.send_message_event(message_event)

    await execute_actions(client, actions.actions)
