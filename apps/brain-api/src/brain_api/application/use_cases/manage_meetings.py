from __future__ import annotations

from uuid import UUID, uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import UnitOfWork
from brain_api.domain.entities import Meeting
from brain_api.domain.enums import MeetingStatus
from grey_cardinal_contracts import MeetingStatusResponse


async def start_meeting(
    uow: UnitOfWork,
    config: AppConfig,
    *,
    telegram_chat_id: int | None = None,
    chat_type: str = "supergroup",
    chat_title: str | None = None,
    external_source: str = "manual",
    title: str | None = None,
    created_by_user_id: UUID | None = None,
    metadata: dict | None = None,
) -> Meeting:
    active = await uow.meetings.get_active_for_chat(telegram_chat_id)
    if active is not None:
        return active

    project = await uow.projects.ensure_default(config.default_workspace_name)
    chat_db_id = None
    if telegram_chat_id is not None:
        chat = await uow.chats.upsert(
            telegram_chat_id=telegram_chat_id,
            chat_type=chat_type,
            title=chat_title,
            project_id=project.id,
        )
        chat_db_id = chat.id

    seq = await uow.meetings.next_sequence()
    meeting = Meeting(
        id=uuid4(),
        public_id=f"MTG-{seq}",
        project_id=project.id,
        telegram_chat_id=chat_db_id,
        external_source=external_source,
        title=title,
        status=MeetingStatus.active,
        started_at=config.now(),
        created_by_user_id=created_by_user_id,
        metadata=metadata or {},
    )
    return await uow.meetings.add(meeting)


async def stop_meeting(uow: UnitOfWork, config: AppConfig, meeting: Meeting) -> Meeting:
    if meeting.status == MeetingStatus.active:
        meeting.status = MeetingStatus.stopped
        meeting.stopped_at = config.now()
        meeting = await uow.meetings.update(meeting)
    return meeting


async def meeting_response(uow: UnitOfWork, meeting: Meeting) -> MeetingStatusResponse:
    chat_id = None
    if meeting.telegram_chat_id is not None:
        chat = await uow.chats.get(meeting.telegram_chat_id)
        chat_id = chat.telegram_chat_id if chat else None
    return MeetingStatusResponse(
        public_id=meeting.public_id,
        status=meeting.status.value,
        title=meeting.title,
        external_source=meeting.external_source,
        telegram_chat_id=chat_id,
        started_at=meeting.started_at,
        stopped_at=meeting.stopped_at,
        transcript_count=await uow.meetings.count_transcripts(meeting.id),
        proposal_count=await uow.meetings.count_proposals(meeting.id),
        metadata=meeting.metadata,
    )
