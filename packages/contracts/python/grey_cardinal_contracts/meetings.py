from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MeetingStatus(StrEnum):
    active = "active"
    stopped = "stopped"
    failed = "failed"


class MeetingStartRequest(BaseModel):
    telegram_chat_id: int | None = None
    external_source: str = "manual"
    title: str | None = None
    created_by_telegram_user_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MeetingStopRequest(BaseModel):
    telegram_chat_id: int | None = None


class MeetingStatusResponse(BaseModel):
    ok: bool = True
    public_id: str
    status: MeetingStatus
    title: str | None = None
    external_source: str | None = None
    telegram_chat_id: int | None = None
    started_at: datetime
    stopped_at: datetime | None = None
    transcript_count: int = 0
    proposal_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class MeetingListResponse(BaseModel):
    items: list[MeetingStatusResponse] = Field(default_factory=list)


class DemoScenarioPayload(BaseModel):
    meeting_id: str | None = None
    delay_seconds: float = 0.0
