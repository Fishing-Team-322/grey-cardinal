"""Контракт websocket-событий brain-api -> frontend-dashboard.

Единый конверт `{"event": <name>, "payload": {...}}`. Имена событий фиксированы
в EventName, чтобы dashboard и brain-api не расходились.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventName(StrEnum):
    task_proposed = "task_proposed"
    task_created = "task_created"
    task_rejected = "task_rejected"
    task_status_changed = "task_status_changed"
    reminder_sent = "reminder_sent"
    transcript_line = "transcript_line"


class WebsocketEvent(BaseModel):
    event: EventName
    payload: dict[str, Any] = Field(default_factory=dict)
