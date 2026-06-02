"""Доменные value objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from brain_api.domain.enums import TaskPriority


@dataclass(frozen=True, slots=True)
class KnownUser:
    """Известный участник чата — подсказка экстрактору."""

    display_name: str
    telegram_username: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractedTask:
    """Результат извлечения задачи из текста (LLM или эвристика)."""

    has_task: bool
    title: str | None = None
    description: str | None = None
    assignee: str | None = None
    deadline: datetime | None = None
    priority: TaskPriority = TaskPriority.medium
    confidence: float = 0.0
    reason: str | None = None
