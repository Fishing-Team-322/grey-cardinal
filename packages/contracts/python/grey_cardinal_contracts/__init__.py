"""Grey Cardinal — общие межсервисные контракты (Pydantic v2).

Импортируется telegram-bot, brain-api и audio-worker, чтобы все сервисы
говорили на одном языке. Frontend использует TypeScript-зеркало этих типов
(см. ../typescript).
"""

from __future__ import annotations

from grey_cardinal_contracts.board import BoardCardResult, BoardProvider
from grey_cardinal_contracts.events import EventName, WebsocketEvent
from grey_cardinal_contracts.tasks import (
    ConfirmationStatus,
    KnownUser,
    TaskDTO,
    TaskExtractionResult,
    TaskListResponse,
    TaskPriority,
    TaskSource,
    TaskStatus,
)
from grey_cardinal_contracts.telegram import (
    ActionsResponse,
    AnswerCallbackAction,
    AnswerCallbackRequest,
    BotAction,
    EditMessageAction,
    EditMessageRequest,
    SendMessageAction,
    SendMessageRequest,
    SendMessageResponse,
    TelegramCallbackEvent,
    TelegramChatInfo,
    TelegramCommandEvent,
    TelegramMessageEvent,
    TelegramMessageRef,
    TelegramSender,
)
from grey_cardinal_contracts.transcripts import TranscriptEvent

__all__ = [
    # board
    "BoardCardResult",
    "BoardProvider",
    # events
    "EventName",
    "WebsocketEvent",
    # tasks
    "ConfirmationStatus",
    "KnownUser",
    "TaskDTO",
    "TaskExtractionResult",
    "TaskListResponse",
    "TaskPriority",
    "TaskSource",
    "TaskStatus",
    # telegram
    "ActionsResponse",
    "AnswerCallbackAction",
    "AnswerCallbackRequest",
    "BotAction",
    "EditMessageAction",
    "EditMessageRequest",
    "SendMessageAction",
    "SendMessageRequest",
    "SendMessageResponse",
    "TelegramCallbackEvent",
    "TelegramChatInfo",
    "TelegramCommandEvent",
    "TelegramMessageEvent",
    "TelegramMessageRef",
    "TelegramSender",
    # transcripts
    "TranscriptEvent",
]
