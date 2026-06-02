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

    def now(self) -> datetime:
        """Текущее время в настроенной таймзоне (tz-aware)."""
        return datetime.now(ZoneInfo(self.timezone))
