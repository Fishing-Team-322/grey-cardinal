"""Desktop client use cases."""

from __future__ import annotations

from uuid import UUID, uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import EventPublisher, TaskExtractor, TelegramGateway, UnitOfWork
from brain_api.application.use_cases.gamification import GamificationService
from brain_api.application.use_cases.ingest_transcript_event import IngestTranscriptEvent
from brain_api.domain.entities import Meeting
from brain_api.domain.enums import MeetingStatus, XpEventKind
from grey_cardinal_contracts import (
    CaptureMode,
    DesktopClientIdentity,
    DesktopGamificationStateResponse,
    DesktopHeartbeatResponse,
    DesktopTranscriptRequest,
    MeetingParticipantDTO,
    RegisterDeviceRequest,
    RegisterDeviceResponse,
    SpeakerIdentitySource,
    TranscriptAsrInfo,
    TranscriptAudioInfo,
    TranscriptEvent,
    TranscriptSourceDetails,
    TranscriptSourceKind,
    TranscriptSpeaker,
    XpEventDTO,
)


async def register_device(
    uow: UnitOfWork, config: AppConfig, request: RegisterDeviceRequest
) -> RegisterDeviceResponse:
    user = await uow.users.upsert_desktop_user(
        request.display_name, telegram_username=request.telegram_username
    )
    workspace_id = UUID(request.workspace_id) if request.workspace_id else None
    device = await uow.devices.upsert(
        user_id=user.id,
        workspace_id=workspace_id,
        device_name=request.device_name,
        platform=request.platform,
        app_version=request.app_version,
        device_fingerprint=request.device_fingerprint,
        now=config.now(),
    )
    session = await uow.client_sessions.start(
        user_id=user.id,
        device_id=device.id,
        workspace_id=workspace_id,
        now=config.now(),
    )
    await uow.commit()
    return RegisterDeviceResponse(
        user_id=str(user.id),
        device_id=str(device.id),
        client_session_id=str(session.id),
        workspace_id=str(workspace_id) if workspace_id else None,
        display_name=user.display_name,
    )


async def resolve_desktop_identity(
    uow: UnitOfWork,
    *,
    user_id: UUID,
    device_id: UUID,
    client_session_id: UUID,
) -> DesktopClientIdentity:
    user = await uow.users.get(user_id)
    device = await uow.devices.get(device_id)
    session = await uow.client_sessions.get(client_session_id)
    if user is None or device is None or session is None:
        raise ValueError("Desktop identity not found")
    if device.user_id != user.id or session.user_id != user.id or session.device_id != device.id:
        raise ValueError("Desktop identity mismatch")
    return DesktopClientIdentity(
        user_id=str(user.id),
        device_id=str(device.id),
        client_session_id=str(session.id),
        workspace_id=str(session.workspace_id) if session.workspace_id else None,
        display_name=user.display_name,
        platform=device.platform,  # type: ignore[arg-type]
        app_version=device.app_version,
    )


async def join_meeting(
    uow: UnitOfWork,
    config: AppConfig,
    identity: DesktopClientIdentity,
    meeting_public_id: str,
    metadata: dict | None = None,
) -> MeetingParticipantDTO:
    meeting = await _ensure_meeting(uow, config, meeting_public_id, identity)
    participant = await uow.meeting_participants.join(
        meeting_id=meeting.id,
        user_id=UUID(identity.user_id),
        device_id=UUID(identity.device_id),
        client_session_id=UUID(identity.client_session_id),
        now=config.now(),
        metadata=metadata or {},
    )
    await GamificationService().grant(
        uow,
        user_id=UUID(identity.user_id),
        workspace_id=UUID(identity.workspace_id) if identity.workspace_id else None,
        meeting_id=meeting.id,
        kind=XpEventKind.meeting_joined,
        reason=f"Joined meeting {meeting.public_id}",
        idempotency_key=f"meeting_joined:{meeting.id}:{identity.user_id}",
    )
    await uow.commit()
    return _participant_dto(participant, meeting.public_id, identity.display_name)


async def leave_meeting(
    uow: UnitOfWork,
    config: AppConfig,
    identity: DesktopClientIdentity,
    meeting_public_id: str,
) -> MeetingParticipantDTO:
    meeting = await uow.meetings.get_by_public_id(meeting_public_id)
    if meeting is None:
        raise ValueError("Meeting not found")
    participant = await uow.meeting_participants.leave(
        meeting.id, UUID(identity.user_id), config.now()
    )
    if participant is None:
        raise ValueError("Participant not found")
    await uow.commit()
    return _participant_dto(participant, meeting.public_id, identity.display_name)


async def heartbeat(
    uow: UnitOfWork,
    config: AppConfig,
    identity: DesktopClientIdentity,
    meeting_public_id: str | None = None,
) -> DesktopHeartbeatResponse:
    meeting = await uow.meetings.get_by_public_id(meeting_public_id) if meeting_public_id else None
    participant = await uow.meeting_participants.touch_active_for_session(
        UUID(identity.client_session_id), config.now(), meeting.id if meeting else None
    )
    await uow.client_sessions.touch(UUID(identity.client_session_id), config.now())
    await uow.devices.touch(UUID(identity.device_id), config.now())
    await uow.commit()
    return DesktopHeartbeatResponse(
        user_id=identity.user_id,
        device_id=identity.device_id,
        client_session_id=identity.client_session_id,
        active_meeting_id=meeting_public_id if participant is not None else None,
    )


async def ingest_desktop_transcript(
    uow: UnitOfWork,
    extractor: TaskExtractor,
    telegram: TelegramGateway,
    events: EventPublisher,
    config: AppConfig,
    identity: DesktopClientIdentity,
    request: DesktopTranscriptRequest,
):
    event = TranscriptEvent(
        meeting_id=request.meeting_id,
        workspace_id=identity.workspace_id,
        speaker_id=identity.user_id,
        speaker_name=identity.display_name,
        speaker=TranscriptSpeaker(
            resolved_user_id=identity.user_id,
            resolved_name=identity.display_name,
            identity_source=SpeakerIdentitySource.authenticated_client,
            identity_confidence=1.0,
        ),
        text=request.text,
        ts=request.ts or config.now(),
        is_final=request.is_final,
        confidence=request.asr_confidence,
        source=TranscriptSourceDetails(
            kind=TranscriptSourceKind.desktop_app,
            user_id=identity.user_id,
            device_id=identity.device_id,
            client_session_id=identity.client_session_id,
            microphone_id=request.microphone_id,
            capture_mode=request.capture_mode or CaptureMode.microphone,
            platform=identity.platform,
            app_version=identity.app_version,
        ),
        asr=TranscriptAsrInfo(provider=request.asr_provider, confidence=request.asr_confidence),
        audio=TranscriptAudioInfo(
            source=request.capture_mode,
            vad_confidence=request.vad_confidence,
            duration_ms=request.duration_ms,
        ),
        raw={
            **request.raw,
            "speaker": {
                "identity_source": SpeakerIdentitySource.authenticated_client.value,
                "identity_confidence": 1.0,
            },
            "source": {
                "kind": TranscriptSourceKind.desktop_app.value,
                "user_id": identity.user_id,
                "device_id": identity.device_id,
                "client_session_id": identity.client_session_id,
                "microphone_id": request.microphone_id,
                "capture_mode": request.capture_mode.value,
            },
        },
    )
    response = await IngestTranscriptEvent(uow, extractor, telegram, events, config).execute(event)
    if response.proposal_created:
        await GamificationService().grant(
            uow,
            user_id=UUID(identity.user_id),
            workspace_id=UUID(identity.workspace_id) if identity.workspace_id else None,
            kind=XpEventKind.task_created_from_speech,
            reason="Created task proposal from desktop speech",
            idempotency_key=f"task_created_from_speech:{response.transcript_id}",
        )
        await uow.commit()
    response.trusted_speaker = True
    return response


async def gamification_state(
    uow: UnitOfWork, identity: DesktopClientIdentity
) -> DesktopGamificationStateResponse:
    total = await uow.gamification.get_total(
        UUID(identity.user_id), UUID(identity.workspace_id) if identity.workspace_id else None
    )
    recent = await uow.gamification.list_recent(UUID(identity.user_id))
    points_total = total.points_total
    if identity.workspace_id is None:
        points_total = max(points_total, sum(event.points for event in recent))
    return DesktopGamificationStateResponse(
        user_id=identity.user_id,
        points_total=points_total,
        level=max(1, (points_total // 100) + 1),
        recent_events=[
            XpEventDTO(
                kind=event.kind.value,
                points=event.points,
                reason=event.reason,
                metadata=event.metadata,
                created_at=event.created_at,
            )
            for event in recent
        ],
    )


async def _ensure_meeting(
    uow: UnitOfWork,
    config: AppConfig,
    public_id: str,
    identity: DesktopClientIdentity,
) -> Meeting:
    meeting = await uow.meetings.get_by_public_id(public_id)
    if meeting is not None:
        return meeting
    project = await uow.projects.ensure_default(config.default_workspace_name)
    meeting = Meeting(
        id=uuid4(),
        public_id=public_id,
        project_id=project.id,
        external_source="desktop_app",
        status=MeetingStatus.active,
        started_at=config.now(),
        created_by_user_id=UUID(identity.user_id),
        metadata={"workspace_id": identity.workspace_id},
    )
    return await uow.meetings.add(meeting)


def _participant_dto(participant, public_id: str, display_name: str) -> MeetingParticipantDTO:
    return MeetingParticipantDTO(
        id=str(participant.id),
        meeting_id=public_id,
        user_id=str(participant.user_id),
        display_name=display_name,
        device_id=str(participant.device_id) if participant.device_id else None,
        client_session_id=str(participant.client_session_id)
        if participant.client_session_id
        else None,
        status=participant.status.value,
        joined_at=participant.joined_at,
        left_at=participant.left_at,
        last_seen_at=participant.last_seen_at,
        metadata=participant.metadata,
    )
