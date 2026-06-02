from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TranscriptSource(StrEnum):
    audio_worker = "audio_worker"
    desktop_agent = "desktop_agent"
    demo = "demo"


class TranscriptEvent(BaseModel):
    type: Literal["transcript"] = "transcript"
    meeting_id: str | None = None
    speaker_id: str | None = None
    speaker_name: str | None = None
    text: str
    ts: datetime
    is_final: bool = True
    confidence: float | None = None
    source: TranscriptSource = TranscriptSource.audio_worker
    raw: dict[str, Any] = Field(default_factory=dict)


class TranscriptIngestResponse(BaseModel):
    ok: bool = True
    transcript_id: str
    meeting_public_id: str | None = None
    proposal_created: bool = False
    telegram_notified: bool = False


class TranscriptDTO(BaseModel):
    id: str
    meeting_id: str | None = None
    meeting_public_id: str | None = None
    speaker_id: str | None = None
    speaker_name: str | None = None
    text: str
    ts: datetime
    is_final: bool
    confidence: float | None = None
    source: TranscriptSource
    raw: dict[str, Any] = Field(default_factory=dict)


class TranscriptListResponse(BaseModel):
    ok: bool = True
    count: int
    items: list[TranscriptDTO] = Field(default_factory=list)

