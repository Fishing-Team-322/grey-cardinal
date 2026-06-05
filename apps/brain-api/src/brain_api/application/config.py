"""Конфиг, нужный use case'ам (подмножество Settings, без зависимости от pydantic)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class AppConfig:
    timezone: str = "Europe/Moscow"
    reminder_deadline_hours_before: int = 2
    reminder_stale_hours: int = 24
    evening_digest_hour: int = 20
    default_workspace_name: str = "Hackathon Team"
    default_telegram_chat_id: int | None = None

    # Политика извлечения задач.
    task_extraction_min_confidence: float = 0.65
    task_extraction_require_action_verb: bool = True

    # Детекция дублей.
    duplicate_similarity_threshold: float = 0.72

    # Анти-спам политика напоминаний.
    reminder_min_interval_minutes: int = 120
    reminder_max_daily_per_user: int = 3
    reminder_quiet_hours_start: str = "22:00"
    reminder_quiet_hours_end: str = "09:00"

    # Dev-only auto-confirm для /demo_core.
    demo_core_auto_confirm: bool = True

    def now(self) -> datetime:
        """Текущее время в настроенной таймзоне (tz-aware)."""
        return datetime.now(ZoneInfo(self.timezone))
