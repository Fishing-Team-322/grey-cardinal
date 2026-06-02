from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .tasks import TaskDTO
from .transcripts import CaptureMode


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
