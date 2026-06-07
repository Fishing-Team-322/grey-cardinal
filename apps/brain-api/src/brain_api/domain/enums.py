"""Доменные перечисления.

Значения совпадают со строковыми значениями в packages/contracts, но домен
намеренно не импортирует contracts, чтобы оставаться без внешних зависимостей.
Маппинг domain <-> contracts делается по значению (.value) в слоях выше.
"""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    backlog = "backlog"
    proposed = "proposed"
    confirmed = "confirmed"
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    review = "review"
    done = "done"
    rejected = "rejected"
    cancelled = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {TaskStatus.done, TaskStatus.rejected, TaskStatus.cancelled}

    @property
    def is_active(self) -> bool:
        """Активная задача — та, что в работе и подлежит напоминаниям/дайджесту."""
        return self in {
            TaskStatus.backlog,
            TaskStatus.todo,
            TaskStatus.in_progress,
            TaskStatus.blocked,
            TaskStatus.review,
        }


class TaskPriority(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TaskSource(StrEnum):
    telegram_chat = "telegram_chat"
    telegram_direct = "telegram_direct"
    meeting_transcript = "meeting_transcript"
    manual = "manual"
    yougile_import = "yougile_import"
    daily_sync = "daily_sync"


class ConfirmationStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"


class BoardProvider(StrEnum):
    yougile = "yougile"
    jira = "jira"
    mock = "mock"


class ReminderKind(StrEnum):
    deadline = "deadline"
    stale = "stale"


class MeetingStatus(StrEnum):
    active = "active"
    stopped = "stopped"
    failed = "failed"


class ClientSessionStatus(StrEnum):
    active = "active"
    revoked = "revoked"
    expired = "expired"


class MeetingParticipantStatus(StrEnum):
    joined = "joined"
    left = "left"
    disconnected = "disconnected"


class XpEventKind(StrEnum):
    task_created_from_speech = "task_created_from_speech"
    task_confirmed = "task_confirmed"
    task_completed = "task_completed"
    status_updated = "status_updated"
    meeting_joined = "meeting_joined"
    meeting_summary_ready = "meeting_summary_ready"
    streak_bonus = "streak_bonus"
    risk_resolved = "risk_resolved"


# Человекочитаемые подписи статусов/приоритетов для русскоязычного UX.
STATUS_LABELS_RU: dict[TaskStatus, str] = {
    TaskStatus.backlog: "Бэклог",
    TaskStatus.proposed: "Предложена",
    TaskStatus.confirmed: "Подтверждена",
    TaskStatus.todo: "To Do",
    TaskStatus.in_progress: "В работе",
    TaskStatus.blocked: "Заблокирована",
    TaskStatus.review: "На проверке",
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
