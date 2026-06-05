from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .tasks import TaskDTO
from .transcripts import CaptureMode, SpeakerIdentitySource, TranscriptSourceKind


class DesktopClientIdentity(BaseModel):
    user_id: str
    device_id: str
    client_session_id: str
    workspace_id: str | None = None
    display_name: str
    platform: Literal["windows", "linux", "macos"]
    app_version: str | None = None


class RegisterDeviceRequest(BaseModel):
    display_name: str
    telegram_username: str | None = None
    device_name: str
    platform: Literal["windows", "linux", "macos"]
    app_version: str | None = None
    device_fingerprint: str | None = None
    workspace_id: str | None = None


class RegisterDeviceResponse(BaseModel):
    user_id: str
    device_id: str
    client_session_id: str
    workspace_id: str | None = None
    display_name: str


class StartClientSessionRequest(BaseModel):
    user_id: str
    device_id: str
    workspace_id: str | None = None


class StartClientSessionResponse(BaseModel):
    client_session_id: str
    status: Literal["active"] = "active"
    expires_at: datetime | None = None


class DesktopHeartbeatRequest(BaseModel):
    meeting_public_id: str | None = None


class DesktopHeartbeatResponse(BaseModel):
    ok: bool = True
    user_id: str
    device_id: str
    client_session_id: str
    active_meeting_id: str | None = None


class JoinMeetingRequest(BaseModel):
    display_name: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class LeaveMeetingRequest(BaseModel):
    reason: str | None = None


class MeetingParticipantDTO(BaseModel):
    id: str
    meeting_id: str
    user_id: str
    display_name: str | None = None
    device_id: str | None = None
    client_session_id: str | None = None
    status: Literal["joined", "left", "disconnected"]
    joined_at: datetime
    left_at: datetime | None = None
    last_seen_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class MeetingParticipantsResponse(BaseModel):
    items: list[MeetingParticipantDTO] = Field(default_factory=list)


class DesktopTranscriptRequest(BaseModel):
    meeting_id: str
    text: str
    ts: datetime | None = None
    is_final: bool = True
    microphone_id: str = "default_input"
    capture_mode: CaptureMode = CaptureMode.microphone
    asr_provider: str = "mock"
    asr_confidence: float | None = None
    vad_confidence: float | None = None
    duration_ms: int | None = None
    raw: dict[str, object] = Field(default_factory=dict)
    payload_source_kind: TranscriptSourceKind | None = Field(default=None, exclude=True)
    payload_source_user_id: str | None = Field(default=None, exclude=True)
    payload_source_device_id: str | None = Field(default=None, exclude=True)
    payload_source_client_session_id: str | None = Field(default=None, exclude=True)
    payload_speaker_identity_source: SpeakerIdentitySource | None = Field(
        default=None, exclude=True
    )
    payload_speaker_identity_confidence: float | None = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def accept_transcript_event_v2_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        if (
            "source" not in value
            and "speaker" not in value
            and "asr" not in value
            and "audio" not in value
        ):
            return value

        def dict_field(name: str) -> dict[str, Any]:
            field = value.get(name)
            return field if isinstance(field, dict) else {}

        source = dict_field("source")
        speaker = dict_field("speaker")
        asr = dict_field("asr")
        audio = dict_field("audio")
        raw = dict_field("raw")

        return {
            "meeting_id": value.get("meeting_id"),
            "text": value.get("text"),
            "ts": value.get("ts"),
            "is_final": value.get("is_final", True),
            "microphone_id": source.get("microphone_id")
            or value.get("microphone_id")
            or "default_input",
            "capture_mode": source.get("capture_mode")
            or audio.get("source")
            or value.get("capture_mode")
            or CaptureMode.microphone,
            "asr_provider": asr.get("provider") or value.get("asr_provider") or "mock",
            "asr_confidence": asr.get("confidence", value.get("asr_confidence")),
            "vad_confidence": audio.get("vad_confidence", value.get("vad_confidence")),
            "duration_ms": audio.get("duration_ms", value.get("duration_ms")),
            "raw": raw,
            "payload_source_kind": source.get("kind"),
            "payload_source_user_id": source.get("user_id"),
            "payload_source_device_id": source.get("device_id"),
            "payload_source_client_session_id": source.get("client_session_id"),
            "payload_speaker_identity_source": speaker.get("identity_source"),
            "payload_speaker_identity_confidence": speaker.get("identity_confidence"),
        }

    @model_validator(mode="after")
    def validate_transcript_event_v2_identity(self) -> DesktopTranscriptRequest:
        if self.payload_source_kind is None:
            return self
        if self.payload_source_kind != TranscriptSourceKind.desktop_app:
            raise ValueError("desktop transcripts require desktop_app source")
        missing = [
            name
            for name, value in (
                ("user_id", self.payload_source_user_id),
                ("device_id", self.payload_source_device_id),
                ("client_session_id", self.payload_source_client_session_id),
            )
            if value in (None, "")
        ]
        if missing:
            raise ValueError("desktop transcripts require " + ", ".join(missing))
        if self.payload_speaker_identity_source != SpeakerIdentitySource.authenticated_client:
            raise ValueError("desktop transcripts require authenticated_client speaker")
        if self.payload_speaker_identity_confidence != 1.0:
            raise ValueError("authenticated_client identity requires confidence 1.0")
        return self


class DesktopTaskListResponse(BaseModel):
    tasks: list[TaskDTO] = Field(default_factory=list)


class XpEventDTO(BaseModel):
    kind: str
    points: int
    reason: str
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None


class DesktopGamificationStateResponse(BaseModel):
    user_id: str
    points_total: int = 0
    level: int = 1
    recent_events: list[XpEventDTO] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Proposals (P4 — demo-ready v0)
# ---------------------------------------------------------------------------


class DesktopProposalDTO(BaseModel):
    """A pending task proposal waiting for confirmation."""

    proposal_id: str
    confirmation_id: str | None = None
    title: str
    description: str | None = None
    assignee_text: str | None = None
    priority: str = "medium"
    raw_text: str
    source: str = "meeting_transcript"
    created_at: datetime | None = None


class DesktopProposalListResponse(BaseModel):
    """Response for GET /desktop/proposals"""

    items: list[DesktopProposalDTO] = Field(default_factory=list)


class DesktopConfirmProposalResponse(BaseModel):
    """Response for POST /desktop/proposals/{id}/confirm"""

    ok: bool = True
    task_public_id: str | None = None
    task_title: str | None = None
    message: str = "proposal confirmed"


class DesktopRejectProposalResponse(BaseModel):
    """Response for POST /desktop/proposals/{id}/reject"""

    ok: bool = True
    message: str = "proposal rejected"


class DesktopTranscriptDTO(BaseModel):
    """A recent desktop transcript event."""

    id: str
    meeting_id: str
    text: str
    asr_provider: str | None = None
    created_at: datetime | None = None


class DesktopRecentTranscriptsResponse(BaseModel):
    """Response for GET /desktop/transcripts/recent"""

    items: list[DesktopTranscriptDTO] = Field(default_factory=list)
