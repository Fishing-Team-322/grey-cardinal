"""Контракт transcript-события от audio-worker -> brain-api.

На P0 audio-worker реальный звук не пишет, но контракт зафиксирован,
чтобы P1-пайплайн подключался без изменения API brain-api.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TranscriptEvent(BaseModel):
    type: Literal["transcript"] = "transcript"
    meeting_id: str | None = None
    speaker_id: str | None = None
    speaker_name: str | None = None
    text: str
    ts: datetime
    is_final: bool = True
    raw: dict[str, Any] = Field(default_factory=dict)
