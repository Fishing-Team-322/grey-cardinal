"""Доменные перечисления.

Значения совпадают со строковыми значениями в packages/contracts, но домен
намеренно не импортирует contracts, чтобы оставаться без внешних зависимостей.
Маппинг domain <-> contracts делается по значению (.value) в слоях выше.
"""

from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    proposed = "proposed"
    confirmed = "confirmed"
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"
    rejected = "rejected"
    cancelled = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {TaskStatus.done, TaskStatus.rejected, TaskStatus.cancelled}

    @property
    def is_active(self) -> bool:
        """Активная задача — та, что в работе и подлежит напоминаниям/дайджесту."""
        return self in {TaskStatus.todo, TaskStatus.in_progress, TaskStatus.blocked}


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


class BoardProvider(str, Enum):
    yougile = "yougile"
    mock = "mock"


class ReminderKind(str, Enum):
    deadline = "deadline"
    stale = "stale"


# Человекочитаемые подписи статусов/приоритетов для русскоязычного UX.
STATUS_LABELS_RU: dict[TaskStatus, str] = {
    TaskStatus.proposed: "Предложена",
    TaskStatus.confirmed: "Подтверждена",
    TaskStatus.todo: "To Do",
    TaskStatus.in_progress: "В работе",
    TaskStatus.blocked: "Заблокирована",
    TaskStatus.done: "Готово",
    TaskStatus.rejected: "Отклонена",
    TaskStatus.cancelled: "Отменена",
}

PRIORITY_LABELS_RU: dict[TaskPriority, str] = {
    TaskPriority.low: "низкий",
    TaskPriority.medium: "средний",
    TaskPriority.high: "высокий",
    TaskPriority.critical: "критический",
}
