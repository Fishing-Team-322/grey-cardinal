from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import EventPublisher, TaskExtractor, TelegramGateway, UnitOfWork
from brain_api.application.use_cases._shared import create_proposal_with_confirmation
from brain_api.application.use_cases.gamification import GamificationService
from brain_api.domain.entities import Meeting, User
from brain_api.domain.entities import TranscriptEvent as TranscriptEntity
from brain_api.domain.enums import ClientSessionStatus, MeetingStatus, TaskSource, XpEventKind
from grey_cardinal_contracts import (
    CaptureMode,
    DesktopGamificationStateResponse,
    DesktopHeartbeatResponse,
    DesktopTaskListResponse,
    DesktopTranscriptRequest,
    EventName,
    KnownUser,
    MeetingParticipantDTO,
    RegisterDeviceRequest,
    RegisterDeviceResponse,
    SpeakerIdentitySource,
    TaskDTO,
    TranscriptAsrInfo,
    TranscriptAudioInfo,
    TranscriptIngestResponse,
    TranscriptSourceDetails,
    TranscriptSourceKind,
    TranscriptSpeaker,
    WebsocketEvent,
    XpEventDTO,
)


@dataclass(frozen=True)
class DesktopIdentity:
    user: User
    device_id: UUID
    client_session_id: UUID
    workspace_id: UUID | None = None


async def register_device(
    uow: UnitOfWork, config: AppConfig, request: RegisterDeviceRequest
) -> RegisterDeviceResponse:
    workspace_uuid = _uuid_or_none(request.workspace_id)
    if workspace_uuid is None:
        workspace_uuid = (await uow.projects.ensure_default(config.default_workspace_name)).id
    user = await uow.users.upsert_desktop_user(request.display_name, request.telegram_username)
    device = await uow.devices.upsert(
        user_id=user.id,
        workspace_id=workspace_uuid,
        device_name=request.device_name,
        platform=request.platform,
        app_version=request.app_version,
        device_fingerprint=request.device_fingerprint,
        now=config.now(),
    )
    session = await uow.client_sessions.start(
        user_id=user.id,
        device_id=device.id,
        workspace_id=workspace_uuid,
        now=config.now(),
    )
    await uow.commit()
    return RegisterDeviceResponse(
        user_id=str(user.id),
        device_id=str(device.id),
        client_session_id=str(session.id),
        workspace_id=str(workspace_uuid) if workspace_uuid else None,
        display_name=user.display_name,
    )


async def resolve_desktop_identity(
    uow: UnitOfWork,
    *,
    user_id: UUID,
    device_id: UUID,
    client_session_id: UUID,
) -> DesktopIdentity:
    user = await uow.users.get(user_id)
    device = await uow.devices.get(device_id)
    session = await uow.client_sessions.get(client_session_id)
    if user is None or device is None or session is None:
        raise ValueError("desktop identity not found")
    if device.user_id != user.id:
        raise ValueError("device does not belong to user")
    if session.user_id != user.id or session.device_id != device.id:
        raise ValueError("client session does not match user/device")
    if session.status != ClientSessionStatus.active:
        raise ValueError("client session is not active")
    return DesktopIdentity(
        user=user,
        device_id=device.id,
        client_session_id=session.id,
        workspace_id=session.workspace_id or device.workspace_id,
    )


async def heartbeat(
    uow: UnitOfWork,
    config: AppConfig,
    identity: DesktopIdentity,
    meeting_public_id: str | None = None,
) -> DesktopHeartbeatResponse:
    now = config.now()
    await uow.devices.touch(identity.device_id, now)
    await uow.client_sessions.touch(identity.client_session_id, now)
    meeting = None
    if meeting_public_id:
        meeting = await uow.meetings.get_by_public_id(meeting_public_id)
    participant = await uow.meeting_participants.touch_active_for_session(
        identity.client_session_id,
        now,
        meeting.id if meeting else None,
    )
    await uow.commit()
    return DesktopHeartbeatResponse(
        user_id=str(identity.user.id),
        device_id=str(identity.device_id),
        client_session_id=str(identity.client_session_id),
        active_meeting_id=meeting_public_id if participant else None,
    )


async def join_meeting(
    uow: UnitOfWork,
    config: AppConfig,
    identity: DesktopIdentity,
    meeting_public_id: str,
    metadata: dict | None = None,
) -> MeetingParticipantDTO:
    meeting = await _ensure_meeting(uow, config, meeting_public_id, identity.user.id)
    participant = await uow.meeting_participants.join(
        meeting_id=meeting.id,
        user_id=identity.user.id,
        device_id=identity.device_id,
        client_session_id=identity.client_session_id,
        now=config.now(),
        metadata=metadata or {},
    )
    await GamificationService().grant(
        uow,
        user_id=identity.user.id,
        workspace_id=identity.workspace_id,
        meeting_id=meeting.id,
        kind=XpEventKind.meeting_joined,
        reason=f"Присоединился к встрече {meeting.public_id}",
        idempotency_key=f"meeting_joined:{meeting.id}:{identity.user.id}",
    )
    await uow.commit()
    return _participant_dto(participant, meeting.public_id, identity.user.display_name)


async def leave_meeting(
    uow: UnitOfWork,
    config: AppConfig,
    identity: DesktopIdentity,
    meeting_public_id: str,
) -> MeetingParticipantDTO:
    meeting = await uow.meetings.get_by_public_id(meeting_public_id)
    if meeting is None:
        raise ValueError("meeting not found")
    participant = await uow.meeting_participants.leave(meeting.id, identity.user.id, config.now())
    if participant is None:
        raise ValueError("meeting participant not found")
    await uow.commit()
    return _participant_dto(participant, meeting.public_id, identity.user.display_name)


async def ingest_desktop_transcript(
    uow: UnitOfWork,
    extractor: TaskExtractor,
    telegram: TelegramGateway,
    events: EventPublisher,
    config: AppConfig,
    identity: DesktopIdentity,
    request: DesktopTranscriptRequest,
) -> TranscriptIngestResponse:
    if request.capture_mode != CaptureMode.microphone:
        raise ValueError("desktop transcripts must use microphone capture mode")
    if request.payload_source_user_id and request.payload_source_user_id != str(identity.user.id):
        raise ValueError("desktop transcript user_id does not match authenticated identity")
    if request.payload_source_device_id and request.payload_source_device_id != str(identity.device_id):
        raise ValueError("desktop transcript device_id does not match authenticated identity")
    if (
        request.payload_source_client_session_id
        and request.payload_source_client_session_id != str(identity.client_session_id)
    ):
        raise ValueError("desktop transcript client_session_id does not match authenticated identity")

    meeting = await _ensure_meeting(uow, config, request.meeting_id, identity.user.id)
    ts = request.ts or config.now()
    device = await uow.devices.get(identity.device_id)
    if device is None:
        raise ValueError("desktop device not found")
    source = TranscriptSourceDetails(
        kind=TranscriptSourceKind.desktop_app,
        user_id=str(identity.user.id),
        device_id=str(identity.device_id),
        client_session_id=str(identity.client_session_id),
        microphone_id=request.microphone_id,
        capture_mode=CaptureMode.microphone,
        platform=device.platform,
        app_version=device.app_version,
    )
    speaker = TranscriptSpeaker(
        resolved_user_id=str(identity.user.id),
        resolved_name=identity.user.display_name,
        identity_source=SpeakerIdentitySource.authenticated_client,
        identity_confidence=1.0,
    )
    raw = {
        **request.raw,
        "source": source.model_dump(mode="json"),
        "speaker": speaker.model_dump(mode="json"),
        "asr": TranscriptAsrInfo(
            provider=request.asr_provider,
            confidence=request.asr_confidence,
        ).model_dump(mode="json"),
        "audio": TranscriptAudioInfo(
            source=CaptureMode.microphone,
            vad_confidence=request.vad_confidence,
            duration_ms=request.duration_ms,
        ).model_dump(mode="json"),
    }
    entity = TranscriptEntity(
        id=uuid4(),
        meeting_id=meeting.public_id,
        meeting_db_id=meeting.id,
        speaker_id=str(identity.user.id),
        speaker_name=identity.user.display_name,
        text=request.text,
        ts=ts,
        is_final=request.is_final,
        confidence=request.asr_confidence,
        source="desktop_app",
        raw_json=raw,
    )
    await uow.transcripts.add(entity)

    await events.publish(
        WebsocketEvent(
            event=EventName.transcript_line,
            payload={
                "meeting_public_id": meeting.public_id,
                "speaker_name": identity.user.display_name,
                "speaker_user_id": str(identity.user.id),
                "identity_source": "authenticated_client",
                "text": request.text,
                "is_final": request.is_final,
            },
        )
    )

    if not request.is_final:
        await uow.commit()
        return TranscriptIngestResponse(
            transcript_id=str(entity.id),
            meeting_public_id=meeting.public_id,
            trusted_speaker=True,
        )

    known_users = [
        KnownUser(display_name=user.display_name, telegram_username=user.telegram_username)
        for user in await uow.users.list_known()
    ]
    extraction = await extractor.extract_task(
        request.text,
        config.now(),
        config.timezone,
        known_users,
    )
    if not extraction.has_task:
        await uow.commit()
        return TranscriptIngestResponse(
            transcript_id=str(entity.id),
            meeting_public_id=meeting.public_id,
            trusted_speaker=True,
        )

    if _is_self_assignment(request.text):
        extraction = extraction.model_copy(
            update={
                "assignee": identity.user.display_name,
                "title": _self_assignment_title(request.text) or extraction.title,
            }
        )

    action = await create_proposal_with_confirmation(
        uow,
        events,
        config,
        source=TaskSource.meeting_transcript,
        raw_text=request.text,
        extraction=extraction,
        chat_telegram_id=None,
        source_transcript_id=entity.id,
    )
    await GamificationService().grant(
        uow,
        user_id=identity.user.id,
        workspace_id=identity.workspace_id,
        meeting_id=meeting.id,
        kind=XpEventKind.task_created_from_speech,
        reason="Создано предложение задачи из речи",
        idempotency_key=f"task_created_from_speech:{entity.id}",
    )
    await uow.commit()
    _ = action
    return TranscriptIngestResponse(
        transcript_id=str(entity.id),
        meeting_public_id=meeting.public_id,
        proposal_created=True,
        telegram_notified=False,
        trusted_speaker=True,
        confirmation_id=_confirmation_id_from_action(action),
    )


async def desktop_tasks(uow: UnitOfWork, identity: DesktopIdentity) -> DesktopTaskListResponse:
    tasks = await uow.tasks.list_for_user(identity.user.id)
    return DesktopTaskListResponse(
        tasks=[
            TaskDTO(
                id=str(task.id),
                public_id=task.public_id,
                title=task.title,
                description=task.description,
                status=task.status.value,
                priority=task.priority.value,
                assignee_text=task.assignee_text,
                deadline=task.deadline,
                source=task.source.value,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
            for task in tasks
        ]
    )


async def gamification_state(
    uow: UnitOfWork, identity: DesktopIdentity
) -> DesktopGamificationStateResponse:
    total = await uow.gamification.get_total(identity.user.id, identity.workspace_id)
    events = await uow.gamification.list_recent(identity.user.id)
    return DesktopGamificationStateResponse(
        user_id=str(identity.user.id),
        points_total=total.points_total,
        level=total.level,
        recent_events=[
            XpEventDTO(
                kind=event.kind.value,
                points=event.points,
                reason=event.reason,
                metadata=event.metadata,
                created_at=event.created_at,
            )
            for event in events
        ],
    )


def _uuid_or_none(value: str | None) -> UUID | None:
    return UUID(value) if value else None


async def _ensure_meeting(
    uow: UnitOfWork, config: AppConfig, public_id: str, user_id: UUID
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
        title=public_id,
        status=MeetingStatus.active,
        started_at=config.now(),
        created_by_user_id=user_id,
        metadata={"desktop_dev": True},
    )
    return await uow.meetings.add(meeting)


def _participant_dto(
    participant,
    meeting_public_id: str,
    display_name: str,
) -> MeetingParticipantDTO:
    return MeetingParticipantDTO(
        id=str(participant.id),
        meeting_id=meeting_public_id,
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


def _is_self_assignment(text: str) -> bool:
    lowered = text.strip().lower()
    return bool(
        re.match(r"^(я\s+(подготовлю|сделаю|возьму|беру)|беру\b)", lowered)
        or "беру на себя" in lowered
        or "на себя" in lowered[:40]
    )


def _self_assignment_title(text: str) -> str | None:
    value = text.strip()
    value = re.sub(r"\s+(до|к)\s+.+$", "", value, flags=re.IGNORECASE).strip()
    replacements = [
        (r"^я\s+подготовлю\s+", "Подготовить "),
        (r"^я\s+сделаю\s+", "Сделать "),
        (r"^я\s+возьму\s+", "Взять "),
        (r"^беру\s+на\s+себя\s+", ""),
        (r"^беру\s+", ""),
    ]
    for pattern, replacement in replacements:
        updated = re.sub(pattern, replacement, value, flags=re.IGNORECASE).strip()
        if updated != value:
            return updated[:1].upper() + updated[1:]
    return None


def _confirmation_id_from_action(action) -> str | None:
    try:
        data = action.reply_markup["inline_keyboard"][0][0]["callback_data"]
    except (KeyError, IndexError, TypeError):
        return None
    if ":" not in data:
        return None
    return data.split(":", 1)[1]
