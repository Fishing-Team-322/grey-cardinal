from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TranscriptSource(StrEnum):
    audio_worker = "audio_worker"
    desktop_agent = "desktop_agent"
    desktop_app = "desktop_app"
    demo = "demo"


class TranscriptSourceKind(StrEnum):
    audio_worker = "audio_worker"
    desktop_app = "desktop_app"
    desktop_agent = "desktop_agent"
    demo = "demo"


class CaptureMode(StrEnum):
    microphone = "microphone"
    system_loopback_experimental = "system_loopback_experimental"
    mixed_meeting_experimental = "mixed_meeting_experimental"
    mock = "mock"


class TranscriptSourceDetails(BaseModel):
    kind: TranscriptSourceKind
    user_id: str | None = None
    device_id: str | None = None
    client_session_id: str | None = None
    microphone_id: str | None = None
    capture_mode: CaptureMode = CaptureMode.microphone
    platform: Literal["windows", "linux", "macos"] | None = None
    app_version: str | None = None


class SpeakerIdentitySource(StrEnum):
    authenticated_client = "authenticated_client"
    legacy_header = "legacy_header"
    unknown = "unknown"


class TranscriptSpeaker(BaseModel):
    resolved_user_id: str | None = None
    resolved_name: str | None = None
    identity_source: SpeakerIdentitySource = SpeakerIdentitySource.unknown
    identity_confidence: float = 0.0

    @model_validator(mode="after")
    def validate_authenticated_confidence(self) -> TranscriptSpeaker:
        if (
            self.identity_source == SpeakerIdentitySource.authenticated_client
            and self.identity_confidence != 1.0
        ):
            raise ValueError("authenticated_client identity requires confidence 1.0")
        return self


class TranscriptAsrInfo(BaseModel):
    provider: str = "mock"
    confidence: float | None = None


class TranscriptAudioInfo(BaseModel):
    source: CaptureMode = CaptureMode.microphone
    vad_confidence: float | None = None
    duration_ms: int | None = None


class TranscriptEvent(BaseModel):
    type: Literal["transcript"] = "transcript"
    meeting_id: str | None = None
    workspace_id: str | None = None
    speaker_id: str | None = None
    speaker_name: str | None = None
    speaker: TranscriptSpeaker | None = None
    text: str
    ts: datetime
    is_final: bool = True
    confidence: float | None = None
    source: TranscriptSource | TranscriptSourceDetails = TranscriptSource.audio_worker
    asr: TranscriptAsrInfo | None = None
    audio: TranscriptAudioInfo | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source", mode="before")
    @classmethod
    def coerce_source(cls, value: object) -> object:
        if isinstance(value, dict):
            return TranscriptSourceDetails.model_validate(value)
        return value

    @model_validator(mode="after")
    def validate_desktop_identity(self) -> TranscriptEvent:
        if (
            isinstance(self.source, TranscriptSourceDetails)
            and self.source.kind == TranscriptSourceKind.desktop_app
        ):
            if self.speaker is None:
                raise ValueError("desktop_app transcripts require speaker identity")
            if self.speaker.identity_source != SpeakerIdentitySource.authenticated_client:
                raise ValueError(
                    "desktop_app transcripts require authenticated_client speaker"
                )
            missing = [
                name
                for name in ("user_id", "device_id", "client_session_id")
                if getattr(self.source, name) in (None, "")
            ]
            if missing:
                raise ValueError("desktop_app transcripts require " + ", ".join(missing))
        return self


class TranscriptIngestResponse(BaseModel):
    ok: bool = True
    transcript_id: str
    meeting_public_id: str | None = None
    proposal_created: bool = False
    telegram_notified: bool = False
    trusted_speaker: bool = False
    confirmation_id: str | None = None


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
    source_payload: dict[str, Any] | None = None
    speaker: TranscriptSpeaker | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class TranscriptListResponse(BaseModel):
    ok: bool = True
    count: int
    items: list[TranscriptDTO] = Field(default_factory=list)

