"""Исполнитель действий brain-api через Telegram Bot API.

Получает список BotAction (send_message / edit_message / answer_callback) и
выполняет их. Это единственное место, где telegram-bot «пишет» в Telegram в
ответ на события.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from grey_cardinal_contracts import BotAction
from telegram_bot.client import TelegramClient

logger = logging.getLogger(__name__)


async def execute_actions(client: TelegramClient, actions: Iterable[BotAction]) -> None:
    for action in actions:
        try:
            await _execute_one(client, action)
        except Exception:
            logger.exception("Failed to execute action %s", getattr(action, "type", "?"))


async def _execute_one(client: TelegramClient, action: BotAction) -> None:
    if action.type == "send_message":
        await client.send_message(action.chat_id, action.text, action.reply_markup)
    elif action.type == "edit_message":
        await client.edit_message_text(
            action.chat_id, action.message_id, action.text, action.reply_markup
        )
    elif action.type == "answer_callback":
        await client.answer_callback_query(action.callback_query_id, action.text, action.show_alert)
    else:  # pragma: no cover
        logger.warning("Unknown action type: %s", action.type)
