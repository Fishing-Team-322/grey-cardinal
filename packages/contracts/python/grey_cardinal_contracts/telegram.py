"""Контракты Telegram-транспорта.

Делятся на две группы:
  1. Нормализованные события telegram-bot -> brain-api
     (TelegramMessageEvent / TelegramCallbackEvent / TelegramCommandEvent).
  2. Действия brain-api -> telegram-bot (BotAction) и запросы reminders
     (SendMessageRequest / SendMessageResponse и т.п.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Общие под-структуры
# --------------------------------------------------------------------------- #
class TelegramChatInfo(BaseModel):
    id: int
    type: str
    title: str | None = None


class TelegramSender(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class TelegramMessageRef(BaseModel):
    message_id: int
    chat_id: int


# --------------------------------------------------------------------------- #
# telegram-bot -> brain-api
# --------------------------------------------------------------------------- #
class TelegramMessageEvent(BaseModel):
    update_id: int
    message_id: int
    chat: TelegramChatInfo
    sender: TelegramSender
    text: str
    date: datetime
    raw: dict[str, Any] = Field(default_factory=dict)


class TelegramCallbackEvent(BaseModel):
    update_id: int
    callback_query_id: str
    from_user: TelegramSender
    message: TelegramMessageRef
    data: str
    raw: dict[str, Any] = Field(default_factory=dict)


class TelegramCommandEvent(BaseModel):
    update_id: int
    message_id: int
    chat: TelegramChatInfo
    sender: TelegramSender
    command: str
    args: list[str] = Field(default_factory=list)
    text: str
    date: datetime
    raw: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# brain-api -> telegram-bot: действия в ответ на событие
# --------------------------------------------------------------------------- #
class SendMessageAction(BaseModel):
    type: Literal["send_message"] = "send_message"
    chat_id: int
    text: str
    reply_markup: dict[str, Any] | None = None
    parse_mode: str | None = None


class EditMessageAction(BaseModel):
    type: Literal["edit_message"] = "edit_message"
    chat_id: int
    message_id: int
    text: str
    reply_markup: dict[str, Any] | None = None
    parse_mode: str | None = None


class AnswerCallbackAction(BaseModel):
    type: Literal["answer_callback"] = "answer_callback"
    callback_query_id: str
    text: str | None = None
    show_alert: bool = False


BotAction = SendMessageAction | EditMessageAction | AnswerCallbackAction


class ActionsResponse(BaseModel):
    """Унифицированный ответ brain-api на любое Telegram-событие."""

    actions: list[BotAction] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# brain-api -> telegram-bot: прямая отправка (reminders / digests)
# --------------------------------------------------------------------------- #
class SendMessageRequest(BaseModel):
    chat_id: int
    text: str
    reply_markup: dict[str, Any] | None = None


class SendMessageResponse(BaseModel):
    ok: bool
    message_id: int | None = None


class EditMessageRequest(BaseModel):
    chat_id: int
    message_id: int
    text: str
    reply_markup: dict[str, Any] | None = None


class AnswerCallbackRequest(BaseModel):
    callback_query_id: str
    text: str | None = None
    show_alert: bool = False
