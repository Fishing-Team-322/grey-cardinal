"""Контракты, связанные с задачами: статусы, приоритеты, источники, DTO задачи
и результат извлечения задачи экстрактором.

Эти типы общие для brain-api (источник истины) и потребителей контрактов.
Доменные enum'ы brain-api зеркалят значения отсюда, но не импортируют этот пакет,
чтобы домен оставался без внешних зависимостей.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    proposed = "proposed"
    confirmed = "confirmed"
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"
    rejected = "rejected"
    cancelled = "cancelled"


class TaskPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TaskSource(str, Enum):
    telegram_chat = "telegram_chat"
    telegram_direct = "telegram_direct"
    meeting_transcript = "meeting_transcript"
    manual = "manual"


class ConfirmationStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"


class KnownUser(BaseModel):
    """Известный участник чата — подсказка экстрактору для матчинга ответственного."""

    display_name: str
    telegram_username: str | None = None


class TaskExtractionResult(BaseModel):
    """Результат работы TaskExtractor (LLM или эвристика)."""

    has_task: bool
    title: str | None = None
    description: str | None = None
    assignee: str | None = None
    deadline: datetime | None = None
    priority: TaskPriority = TaskPriority.medium
    confidence: float = 0.0
    reason: str | None = None


class TaskDTO(BaseModel):
    """Представление задачи во внешних API (internal/tasks, websocket payloads)."""

    id: str
    public_id: str
    title: str
    description: str | None = None
    status: TaskStatus
    priority: TaskPriority
    assignee_text: str | None = None
    deadline: datetime | None = None
    source: TaskSource
    board_provider: str | None = None
    board_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TaskListResponse(BaseModel):
    tasks: list[TaskDTO] = Field(default_factory=list)
