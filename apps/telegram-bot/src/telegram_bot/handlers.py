"""Нормализация Telegram-update в контрактные события для brain-api."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from grey_cardinal_contracts import (
    TelegramCallbackEvent,
    TelegramChatInfo,
    TelegramCommandEvent,
    TelegramEntity,
    TelegramMessageEvent,
    TelegramMessageRef,
    TelegramSender,
)
from telegram_bot.commands import parse_command


def _ts(value: int | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return datetime.fromtimestamp(value, tz=UTC)


def _sender(raw: dict[str, Any]) -> TelegramSender:
    return TelegramSender(
        id=raw.get("id", 0),
        username=raw.get("username"),
        first_name=raw.get("first_name"),
        last_name=raw.get("last_name"),
    )


def _chat(raw: dict[str, Any]) -> TelegramChatInfo:
    return TelegramChatInfo(
        id=raw.get("id", 0),
        type=raw.get("type", "private"),
        title=raw.get("title"),
    )


def _entities(message: dict[str, Any]) -> list[TelegramEntity]:
    return [
        TelegramEntity(
            type=str(item.get("type") or ""),
            offset=int(item.get("offset") or 0),
            length=int(item.get("length") or 0),
            user=_sender(item["user"]) if item.get("user") else None,
        )
        for item in (message.get("entities") or [])
    ]


def _reply(message: dict[str, Any]) -> dict[str, Any]:
    reply = message.get("reply_to_message") or {}
    reply_sender = reply.get("from") or reply.get("sender_chat")
    return {
        "reply_to_message_id": reply.get("message_id"),
        "reply_to_sender": _sender(reply_sender) if reply_sender else None,
        "reply_to_text": reply.get("text") or reply.get("caption"),
        "message_thread_id": message.get("message_thread_id"),
    }


def build_message_event(update: dict[str, Any], message: dict[str, Any]) -> TelegramMessageEvent:
    sender_raw = message.get("from") or message.get("sender_chat") or {}
    return TelegramMessageEvent(
        update_id=update.get("update_id", 0),
        message_id=message.get("message_id", 0),
        chat=_chat(message.get("chat", {})),
        sender=_sender(sender_raw),
        text=message.get("text", ""),
        date=_ts(message.get("date")),
        entities=_entities(message),
        **_reply(message),
        raw=update,
    )


def build_command_event(update: dict[str, Any], message: dict[str, Any]) -> TelegramCommandEvent:
    text = message.get("text", "")
    command, args = parse_command(text)
    sender_raw = message.get("from") or message.get("sender_chat") or {}
    return TelegramCommandEvent(
        update_id=update.get("update_id", 0),
        message_id=message.get("message_id", 0),
        chat=_chat(message.get("chat", {})),
        sender=_sender(sender_raw),
        command=command,
        args=args,
        text=text,
        date=_ts(message.get("date")),
        entities=_entities(message),
        **_reply(message),
        raw=update,
    )


def build_callback_event(
    update: dict[str, Any], callback_query: dict[str, Any]
) -> TelegramCallbackEvent:
    message = callback_query.get("message", {}) or {}
    chat = message.get("chat", {}) or {}
    return TelegramCallbackEvent(
        update_id=update.get("update_id", 0),
        callback_query_id=callback_query.get("id", ""),
        from_user=_sender(callback_query.get("from", {})),
        message=TelegramMessageRef(
            message_id=message.get("message_id", 0),
            chat_id=chat.get("id", 0),
        ),
        data=callback_query.get("data", ""),
        raw=update,
    )
