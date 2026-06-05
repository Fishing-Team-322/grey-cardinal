"""Конкретные репозитории (SQLAlchemy) и UnitOfWork.

Репозитории маппят ORM-модели в доменные сущности и обратно, чтобы домен и
use cases не зависели от SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from brain_api.domain.entities import (
    AuditLog,
    BoardCard,
    ChatMessage,
    ClientSession,
    Confirmation,
    Device,
    DigestLog,
    Meeting,
    MeetingParticipant,
    Project,
    ReminderLog,
    Task,
    TaskProposal,
    TelegramChat,
    TranscriptEvent,
    User,
    UserXpEvent,
    UserXpTotal,
)
from brain_api.domain.enums import (
    BoardProvider,
    ClientSessionStatus,
    ConfirmationStatus,
    MeetingParticipantStatus,
    MeetingStatus,
    ReminderKind,
    TaskPriority,
    TaskSource,
    TaskStatus,
    XpEventKind,
)
from brain_api.domain.services import parse_public_id
from brain_api.infrastructure.db import models as m

_ACTIVE_STATUSES = [TaskStatus.todo.value, TaskStatus.in_progress.value, TaskStatus.blocked.value]
_TERMINAL_STATUSES = [
    TaskStatus.done.value,
    TaskStatus.rejected.value,
    TaskStatus.cancelled.value,
]


# --------------------------------------------------------------------------- #
# Мапперы ORM -> domain
# --------------------------------------------------------------------------- #
def _user(row: m.UserModel) -> User:
    return User(
        id=row.id,
        display_name=row.display_name,
        telegram_user_id=row.telegram_user_id,
        telegram_username=row.telegram_username,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _device(row: m.DeviceModel) -> Device:
    return Device(
        id=row.id,
        user_id=row.user_id,
        workspace_id=row.workspace_id,
        device_name=row.device_name,
        platform=row.platform,
        app_version=row.app_version,
        device_fingerprint=row.device_fingerprint,
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _client_session(row: m.ClientSessionModel) -> ClientSession:
    return ClientSession(
        id=row.id,
        user_id=row.user_id,
        device_id=row.device_id,
        workspace_id=row.workspace_id,
        session_token_hash=row.session_token_hash,
        status=ClientSessionStatus(row.status),
        started_at=row.started_at,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _project(row: m.ProjectModel) -> Project:
    return Project(
        id=row.id,
        name=row.name,
        default_chat_id=row.default_chat_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _chat(row: m.TelegramChatModel) -> TelegramChat:
    return TelegramChat(
        id=row.id,
        telegram_chat_id=row.telegram_chat_id,
        type=row.type,
        title=row.title,
        project_id=row.project_id,
        task_confirmation_required=row.task_confirmation_required,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message(row: m.ChatMessageModel) -> ChatMessage:
    return ChatMessage(
        id=row.id,
        telegram_message_id=row.telegram_message_id,
        chat_id=row.chat_id,
        sender_id=row.sender_id,
        text=row.text,
        raw_json=row.raw_json or {},
        created_at=row.created_at,
    )


def _meeting(row: m.MeetingModel) -> Meeting:
    return Meeting(
        id=row.id,
        public_id=row.public_id,
        project_id=row.project_id,
        telegram_chat_id=row.telegram_chat_id,
        external_source=row.external_source,
        title=row.title,
        status=MeetingStatus(row.status),
        started_at=row.started_at,
        stopped_at=row.stopped_at,
        created_by_user_id=row.created_by_user_id,
        metadata=row.metadata_json or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _meeting_participant(row: m.MeetingParticipantModel) -> MeetingParticipant:
    return MeetingParticipant(
        id=row.id,
        meeting_id=row.meeting_id,
        user_id=row.user_id,
        device_id=row.device_id,
        client_session_id=row.client_session_id,
        status=MeetingParticipantStatus(row.status),
        joined_at=row.joined_at,
        left_at=row.left_at,
        last_seen_at=row.last_seen_at,
        metadata=row.metadata_json or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _proposal(row: m.TaskProposalModel) -> TaskProposal:
    return TaskProposal(
        id=row.id,
        source=TaskSource(row.source),
        title=row.title,
        priority=TaskPriority(row.priority),
        confidence=row.confidence,
        raw_text=row.raw_text,
        extractor_payload=row.extractor_payload or {},
        description=row.description,
        source_message_id=row.source_message_id,
        source_transcript_id=row.source_transcript_id,
        assignee_text=row.assignee_text,
        assignee_id=row.assignee_id,
        deadline=row.deadline,
        created_at=row.created_at,
    )


def _confirmation(row: m.ConfirmationModel) -> Confirmation:
    return Confirmation(
        id=row.id,
        proposal_id=row.proposal_id,
        status=ConfirmationStatus(row.status),
        telegram_chat_id=row.telegram_chat_id,
        telegram_message_id=row.telegram_message_id,
        created_task_id=row.created_task_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        expires_at=row.expires_at,
    )


def _task(row: m.TaskModel) -> Task:
    return Task(
        id=row.id,
        public_id=row.public_id,
        title=row.title,
        status=TaskStatus(row.status),
        priority=TaskPriority(row.priority),
        source=TaskSource(row.source),
        project_id=row.project_id,
        description=row.description,
        assignee_id=row.assignee_id,
        assignee_text=row.assignee_text,
        deadline=row.deadline,
        source_message_id=row.source_message_id,
        created_from_proposal_id=row.created_from_proposal_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
        last_status_update_at=row.last_status_update_at,
    )


def _board_card(row: m.BoardCardModel) -> BoardCard:
    return BoardCard(
        id=row.id,
        task_id=row.task_id,
        provider=BoardProvider(row.provider),
        external_card_id=row.external_card_id,
        external_url=row.external_url,
        external_payload=row.external_payload,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _transcript_event(row: m.TranscriptEventModel) -> TranscriptEvent:
    return TranscriptEvent(
        id=row.id,
        meeting_db_id=row.meeting_db_id,
        meeting_id=row.meeting_id,
        speaker_id=row.speaker_id,
        speaker_name=row.speaker_name,
        text=row.text,
        ts=row.ts,
        is_final=row.is_final,
        confidence=row.confidence,
        source=row.source,
        raw_json=row.raw_json,
        created_at=row.created_at,
    )


def _xp_event(row: m.UserXpEventModel) -> UserXpEvent:
    return UserXpEvent(
        id=row.id,
        user_id=row.user_id,
        workspace_id=row.workspace_id,
        task_id=row.task_id,
        meeting_id=row.meeting_id,
        kind=XpEventKind(row.kind),
        points=row.points,
        reason=row.reason,
        metadata=row.metadata_json or {},
        created_at=row.created_at,
    )


def _xp_total(row: m.UserXpTotalModel) -> UserXpTotal:
    return UserXpTotal(
        id=row.id,
        user_id=row.user_id,
        workspace_id=row.workspace_id,
        points_total=row.points_total,
        level=row.level,
        updated_at=row.updated_at,
    )


# --------------------------------------------------------------------------- #
# Репозитории
# --------------------------------------------------------------------------- #
class UserRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        row = await self._s.scalar(
            select(m.UserModel).where(m.UserModel.telegram_user_id == telegram_user_id)
        )
        return _user(row) if row else None

    async def upsert_from_telegram(
        self, telegram_user_id: int, username: str | None, display_name: str
    ) -> User:
        row = await self._s.scalar(
            select(m.UserModel).where(m.UserModel.telegram_user_id == telegram_user_id)
        )
        if row is None:
            row = m.UserModel(
                id=uuid4(),
                telegram_user_id=telegram_user_id,
                telegram_username=username,
                display_name=display_name,
            )
            self._s.add(row)
        else:
            row.telegram_username = username
            row.display_name = display_name
        await self._s.flush()
        await self._s.refresh(row)
        return _user(row)

    async def get(self, user_id: UUID) -> User | None:
        row = await self._s.get(m.UserModel, user_id)
        return _user(row) if row else None

    async def upsert_desktop_user(
        self, display_name: str, telegram_username: str | None = None
    ) -> User:
        statement = select(m.UserModel)
        if telegram_username:
            statement = statement.where(m.UserModel.telegram_username == telegram_username)
        else:
            statement = statement.where(m.UserModel.display_name == display_name)
        row = await self._s.scalar(statement)
        if row is None:
            row = m.UserModel(
                id=uuid4(),
                telegram_user_id=None,
                telegram_username=telegram_username,
                display_name=display_name,
            )
            self._s.add(row)
        else:
            row.display_name = display_name
            if telegram_username:
                row.telegram_username = telegram_username
        await self._s.flush()
        await self._s.refresh(row)
        return _user(row)

    async def get_by_display_name(self, display_name: str) -> User | None:
        row = await self._s.scalar(
            select(m.UserModel).where(func.lower(m.UserModel.display_name) == display_name.lower())
        )
        return _user(row) if row else None

    async def list_known(self, limit: int = 50) -> list[User]:
        rows = await self._s.scalars(select(m.UserModel).limit(limit))
        return [_user(r) for r in rows]


class DeviceRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, device_id: UUID) -> Device | None:
        row = await self._s.get(m.DeviceModel, device_id)
        return _device(row) if row else None

    async def upsert(
        self,
        *,
        user_id: UUID,
        device_name: str,
        platform: str,
        workspace_id: UUID | None = None,
        app_version: str | None = None,
        device_fingerprint: str | None = None,
        now: datetime | None = None,
    ) -> Device:
        statement = select(m.DeviceModel).where(m.DeviceModel.user_id == user_id)
        if device_fingerprint:
            statement = statement.where(m.DeviceModel.device_fingerprint == device_fingerprint)
        else:
            statement = statement.where(
                m.DeviceModel.device_name == device_name,
                m.DeviceModel.platform == platform,
            )
        row = await self._s.scalar(statement)
        if row is None:
            row = m.DeviceModel(
                id=uuid4(),
                user_id=user_id,
                workspace_id=workspace_id,
                device_name=device_name,
                platform=platform,
                app_version=app_version,
                device_fingerprint=device_fingerprint,
                last_seen_at=now,
            )
            self._s.add(row)
        else:
            row.device_name = device_name
            row.platform = platform
            row.workspace_id = workspace_id
            row.app_version = app_version
            row.device_fingerprint = device_fingerprint or row.device_fingerprint
            row.last_seen_at = now or row.last_seen_at
        await self._s.flush()
        await self._s.refresh(row)
        return _device(row)

    async def touch(self, device_id: UUID, now: datetime) -> Device | None:
        row = await self._s.get(m.DeviceModel, device_id)
        if row is None:
            return None
        row.last_seen_at = now
        await self._s.flush()
        await self._s.refresh(row)
        return _device(row)


class ClientSessionRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, session_id: UUID) -> ClientSession | None:
        row = await self._s.get(m.ClientSessionModel, session_id)
        return _client_session(row) if row else None

    async def start(
        self,
        *,
        user_id: UUID,
        device_id: UUID | None,
        workspace_id: UUID | None,
        now: datetime,
        expires_at: datetime | None = None,
    ) -> ClientSession:
        row = m.ClientSessionModel(
            id=uuid4(),
            user_id=user_id,
            device_id=device_id,
            workspace_id=workspace_id,
            status=ClientSessionStatus.active.value,
            started_at=now,
            last_seen_at=now,
            expires_at=expires_at,
        )
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return _client_session(row)

    async def touch(self, session_id: UUID, now: datetime) -> ClientSession | None:
        row = await self._s.get(m.ClientSessionModel, session_id)
        if row is None:
            return None
        row.last_seen_at = now
        await self._s.flush()
        await self._s.refresh(row)
        return _client_session(row)


class ProjectRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def ensure_default(self, name: str = "Hackathon Team") -> Project:
        row = await self._s.scalar(select(m.ProjectModel).order_by(m.ProjectModel.created_at))
        if row is None:
            row = m.ProjectModel(id=uuid4(), name=name)
            self._s.add(row)
            await self._s.flush()
        elif row.name == "Default" and name:
            row.name = name
            await self._s.flush()
            await self._s.refresh(row)
        return _project(row)

    async def set_default_chat(self, project_id: UUID, chat_id: UUID) -> Project:
        row = await self._s.get(m.ProjectModel, project_id)
        if row is None:
            raise ValueError(f"Project {project_id} not found")
        row.default_chat_id = chat_id
        await self._s.flush()
        await self._s.refresh(row)
        return _project(row)


class ChatRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert(
        self,
        telegram_chat_id: int,
        chat_type: str,
        title: str | None,
        project_id: UUID | None,
    ) -> TelegramChat:
        row = await self._s.scalar(
            select(m.TelegramChatModel).where(
                m.TelegramChatModel.telegram_chat_id == telegram_chat_id
            )
        )
        if row is None:
            row = m.TelegramChatModel(
                id=uuid4(),
                telegram_chat_id=telegram_chat_id,
                type=chat_type,
                title=title,
                project_id=project_id,
            )
            self._s.add(row)
        else:
            row.type = chat_type
            row.title = title
            if project_id is not None:
                row.project_id = project_id
        await self._s.flush()
        await self._s.refresh(row)

        # Привязываем чат как чат по умолчанию проекту (для reminders/digest).
        if project_id is not None:
            project = await self._s.get(m.ProjectModel, project_id)
            if project is not None and project.default_chat_id is None:
                project.default_chat_id = row.id
                await self._s.flush()
        return _chat(row)

    async def get_by_telegram_id(self, telegram_chat_id: int) -> TelegramChat | None:
        row = await self._s.scalar(
            select(m.TelegramChatModel).where(
                m.TelegramChatModel.telegram_chat_id == telegram_chat_id
            )
        )
        return _chat(row) if row else None

    async def set_confirmation_required(
        self, telegram_chat_id: int, required: bool
    ) -> TelegramChat:
        row = await self._s.scalar(
            select(m.TelegramChatModel).where(
                m.TelegramChatModel.telegram_chat_id == telegram_chat_id
            )
        )
        if row is None:
            row = m.TelegramChatModel(
                id=uuid4(),
                telegram_chat_id=telegram_chat_id,
                type="supergroup",
                title=None,
                project_id=None,
                task_confirmation_required=required,
            )
            self._s.add(row)
        else:
            row.task_confirmation_required = required
        await self._s.flush()
        await self._s.refresh(row)
        return _chat(row)

    async def get(self, chat_id: UUID) -> TelegramChat | None:
        row = await self._s.get(m.TelegramChatModel, chat_id)
        return _chat(row) if row else None

    async def list_for_project(self, project_id: UUID) -> list[TelegramChat]:
        rows = await self._s.scalars(
            select(m.TelegramChatModel)
            .where(m.TelegramChatModel.project_id == project_id)
            .order_by(m.TelegramChatModel.created_at)
        )
        return [_chat(row) for row in rows]


class MeetingRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, meeting: Meeting) -> Meeting:
        seq = int(meeting.public_id.removeprefix("MTG-"))
        row = m.MeetingModel(
            id=meeting.id,
            seq=seq,
            public_id=meeting.public_id,
            project_id=meeting.project_id,
            telegram_chat_id=meeting.telegram_chat_id,
            external_source=meeting.external_source,
            title=meeting.title,
            status=meeting.status.value,
            started_at=meeting.started_at,
            stopped_at=meeting.stopped_at,
            created_by_user_id=meeting.created_by_user_id,
            metadata_json=meeting.metadata,
        )
        self._s.add(row)
        await self._s.flush()
        return _meeting(row)

    async def get_by_public_id(self, public_id: str) -> Meeting | None:
        row = await self._s.scalar(
            select(m.MeetingModel).where(m.MeetingModel.public_id == public_id)
        )
        return _meeting(row) if row else None

    async def get(self, meeting_id: UUID) -> Meeting | None:
        row = await self._s.get(m.MeetingModel, meeting_id)
        return _meeting(row) if row else None

    async def get_active_for_chat(self, telegram_chat_id: int | None) -> Meeting | None:
        statement = (
            select(m.MeetingModel)
            .outerjoin(
                m.TelegramChatModel,
                m.TelegramChatModel.id == m.MeetingModel.telegram_chat_id,
            )
            .where(m.MeetingModel.status == MeetingStatus.active.value)
            .order_by(m.MeetingModel.started_at.desc())
        )
        if telegram_chat_id is not None:
            statement = statement.where(m.TelegramChatModel.telegram_chat_id == telegram_chat_id)
        row = await self._s.scalar(statement)
        return _meeting(row) if row else None

    async def list_recent(self, limit: int = 20) -> list[Meeting]:
        rows = await self._s.scalars(
            select(m.MeetingModel)
            .order_by(m.MeetingModel.started_at.desc())
            .limit(max(1, min(limit, 100)))
        )
        return [_meeting(row) for row in rows]

    async def next_sequence(self) -> int:
        current = await self._s.scalar(select(func.max(m.MeetingModel.seq)))
        return (current or 0) + 1

    async def update(self, meeting: Meeting) -> Meeting:
        row = await self._s.get(m.MeetingModel, meeting.id)
        if row is None:
            raise ValueError(f"Meeting {meeting.id} not found")
        row.status = meeting.status.value
        row.stopped_at = meeting.stopped_at
        row.metadata_json = meeting.metadata
        await self._s.flush()
        await self._s.refresh(row)
        return _meeting(row)

    async def count_transcripts(self, meeting_id: UUID) -> int:
        value = await self._s.scalar(
            select(func.count())
            .select_from(m.TranscriptEventModel)
            .where(m.TranscriptEventModel.meeting_db_id == meeting_id)
        )
        return int(value or 0)

    async def count_proposals(self, meeting_id: UUID) -> int:
        value = await self._s.scalar(
            select(func.count())
            .select_from(m.TaskProposalModel)
            .join(
                m.TranscriptEventModel,
                m.TranscriptEventModel.id == m.TaskProposalModel.source_transcript_id,
            )
            .where(m.TranscriptEventModel.meeting_db_id == meeting_id)
        )
        return int(value or 0)


class MeetingParticipantRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def join(
        self,
        *,
        meeting_id: UUID,
        user_id: UUID,
        device_id: UUID | None,
        client_session_id: UUID | None,
        now: datetime,
        metadata: dict | None = None,
    ) -> MeetingParticipant:
        row = await self._s.scalar(
            select(m.MeetingParticipantModel).where(
                m.MeetingParticipantModel.meeting_id == meeting_id,
                m.MeetingParticipantModel.user_id == user_id,
            )
        )
        if row is None:
            row = m.MeetingParticipantModel(
                id=uuid4(),
                meeting_id=meeting_id,
                user_id=user_id,
                device_id=device_id,
                client_session_id=client_session_id,
                status=MeetingParticipantStatus.joined.value,
                joined_at=now,
                last_seen_at=now,
                metadata_json=metadata or {},
            )
            self._s.add(row)
        else:
            row.device_id = device_id
            row.client_session_id = client_session_id
            row.status = MeetingParticipantStatus.joined.value
            row.left_at = None
            row.last_seen_at = now
            row.metadata_json = metadata or row.metadata_json or {}
        await self._s.flush()
        await self._s.refresh(row)
        return _meeting_participant(row)

    async def leave(
        self,
        meeting_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> MeetingParticipant | None:
        row = await self._s.scalar(
            select(m.MeetingParticipantModel).where(
                m.MeetingParticipantModel.meeting_id == meeting_id,
                m.MeetingParticipantModel.user_id == user_id,
            )
        )
        if row is None:
            return None
        row.status = MeetingParticipantStatus.left.value
        row.left_at = now
        row.last_seen_at = now
        await self._s.flush()
        await self._s.refresh(row)
        return _meeting_participant(row)

    async def touch_active_for_session(
        self, client_session_id: UUID, now: datetime, meeting_id: UUID | None = None
    ) -> MeetingParticipant | None:
        statement = select(m.MeetingParticipantModel).where(
            m.MeetingParticipantModel.client_session_id == client_session_id,
            m.MeetingParticipantModel.status == MeetingParticipantStatus.joined.value,
        )
        if meeting_id is not None:
            statement = statement.where(m.MeetingParticipantModel.meeting_id == meeting_id)
        row = await self._s.scalar(statement.order_by(m.MeetingParticipantModel.joined_at.desc()))
        if row is None:
            return None
        row.last_seen_at = now
        await self._s.flush()
        await self._s.refresh(row)
        return _meeting_participant(row)

    async def list_for_meeting(self, meeting_id: UUID) -> list[MeetingParticipant]:
        rows = await self._s.scalars(
            select(m.MeetingParticipantModel)
            .where(m.MeetingParticipantModel.meeting_id == meeting_id)
            .order_by(m.MeetingParticipantModel.joined_at)
        )
        return [_meeting_participant(row) for row in rows]


class MessageRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_tg(self, chat_id: UUID, telegram_message_id: int) -> ChatMessage | None:
        row = await self._s.scalar(
            select(m.ChatMessageModel).where(
                m.ChatMessageModel.chat_id == chat_id,
                m.ChatMessageModel.telegram_message_id == telegram_message_id,
            )
        )
        return _message(row) if row else None

    async def add(self, message: ChatMessage) -> ChatMessage:
        row = m.ChatMessageModel(
            id=message.id,
            telegram_message_id=message.telegram_message_id,
            chat_id=message.chat_id,
            sender_id=message.sender_id,
            text=message.text,
            raw_json=message.raw_json or {},
        )
        self._s.add(row)
        await self._s.flush()
        return _message(row)

    async def list_recent_for_chat(self, chat_id: UUID, limit: int = 8) -> list[ChatMessage]:
        rows = await self._s.scalars(
            select(m.ChatMessageModel)
            .where(m.ChatMessageModel.chat_id == chat_id)
            .order_by(
                m.ChatMessageModel.created_at.desc(),
                m.ChatMessageModel.telegram_message_id.desc(),
            )
            .limit(max(1, min(limit, 20)))
        )
        return list(reversed([_message(row) for row in rows]))


class ProposalRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, proposal: TaskProposal) -> TaskProposal:
        row = m.TaskProposalModel(
            id=proposal.id,
            source=proposal.source.value,
            source_message_id=proposal.source_message_id,
            source_transcript_id=proposal.source_transcript_id,
            title=proposal.title,
            description=proposal.description,
            assignee_text=proposal.assignee_text,
            assignee_id=proposal.assignee_id,
            deadline=proposal.deadline,
            priority=proposal.priority.value,
            confidence=proposal.confidence,
            raw_text=proposal.raw_text,
            extractor_payload=proposal.extractor_payload or {},
        )
        self._s.add(row)
        await self._s.flush()
        return _proposal(row)

    async def get(self, proposal_id: UUID) -> TaskProposal | None:
        row = await self._s.get(m.TaskProposalModel, proposal_id)
        return _proposal(row) if row else None

    async def get_by_source_message(self, message_id: UUID) -> TaskProposal | None:
        row = await self._s.scalar(
            select(m.TaskProposalModel).where(m.TaskProposalModel.source_message_id == message_id)
        )
        return _proposal(row) if row else None

    async def list_pending_for_user(self, user_id: UUID, limit: int = 20) -> list[TaskProposal]:
        """Return proposals whose pending confirmation belongs to this user via transcript."""
        rows = await self._s.scalars(
            select(m.TaskProposalModel)
            .join(
                m.ConfirmationModel,
                m.ConfirmationModel.proposal_id == m.TaskProposalModel.id,
            )
            .join(
                m.TranscriptEventModel,
                m.TranscriptEventModel.id == m.TaskProposalModel.source_transcript_id,
                isouter=True,
            )
            .where(
                m.ConfirmationModel.status == "pending",
                m.TranscriptEventModel.speaker_id == str(user_id),
            )
            .order_by(m.TaskProposalModel.created_at.desc())
            .limit(limit)
        )
        return [_proposal(r) for r in rows]


class ConfirmationRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, confirmation: Confirmation) -> Confirmation:
        row = m.ConfirmationModel(
            id=confirmation.id,
            proposal_id=confirmation.proposal_id,
            status=confirmation.status.value,
            telegram_chat_id=confirmation.telegram_chat_id,
            telegram_message_id=confirmation.telegram_message_id,
            created_task_id=confirmation.created_task_id,
            expires_at=confirmation.expires_at,
        )
        self._s.add(row)
        await self._s.flush()
        return _confirmation(row)

    async def get(self, confirmation_id: UUID) -> Confirmation | None:
        row = await self._s.get(m.ConfirmationModel, confirmation_id)
        return _confirmation(row) if row else None

    async def update(self, confirmation: Confirmation) -> Confirmation:
        row = await self._s.get(m.ConfirmationModel, confirmation.id)
        if row is None:
            raise ValueError(f"Confirmation {confirmation.id} not found")
        row.status = confirmation.status.value
        row.telegram_chat_id = confirmation.telegram_chat_id
        row.telegram_message_id = confirmation.telegram_message_id
        row.created_task_id = confirmation.created_task_id
        await self._s.flush()
        await self._s.refresh(row)
        return _confirmation(row)

    async def get_pending_for_proposal(self, proposal_id: UUID) -> Confirmation | None:
        row = await self._s.scalar(
            select(m.ConfirmationModel).where(
                m.ConfirmationModel.proposal_id == proposal_id,
                m.ConfirmationModel.status == "pending",
            )
        )
        return _confirmation(row) if row else None


class TaskRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, task: Task) -> Task:
        seq = parse_public_id(task.public_id) or 1
        row = m.TaskModel(
            id=task.id,
            seq=seq,
            public_id=task.public_id,
            project_id=task.project_id,
            title=task.title,
            description=task.description,
            status=task.status.value,
            priority=task.priority.value,
            assignee_id=task.assignee_id,
            assignee_text=task.assignee_text,
            deadline=task.deadline,
            source=task.source.value,
            source_message_id=task.source_message_id,
            created_from_proposal_id=task.created_from_proposal_id,
            completed_at=task.completed_at,
            last_status_update_at=task.last_status_update_at,
        )
        self._s.add(row)
        await self._s.flush()
        return _task(row)

    async def get(self, task_id: UUID) -> Task | None:
        row = await self._s.get(m.TaskModel, task_id)
        return _task(row) if row else None

    async def get_by_public_id(self, public_id: str) -> Task | None:
        row = await self._s.scalar(select(m.TaskModel).where(m.TaskModel.public_id == public_id))
        return _task(row) if row else None

    async def next_sequence(self) -> int:
        current = await self._s.scalar(select(func.max(m.TaskModel.seq)))
        return (current or 0) + 1

    async def update(self, task: Task) -> Task:
        row = await self._s.get(m.TaskModel, task.id)
        if row is None:
            raise ValueError(f"Task {task.id} not found")
        row.title = task.title
        row.description = task.description
        row.status = task.status.value
        row.priority = task.priority.value
        row.assignee_id = task.assignee_id
        row.assignee_text = task.assignee_text
        row.deadline = task.deadline
        row.completed_at = task.completed_at
        row.last_status_update_at = task.last_status_update_at
        await self._s.flush()
        await self._s.refresh(row)
        return _task(row)

    async def list_active(self) -> list[Task]:
        rows = await self._s.scalars(
            select(m.TaskModel)
            .where(m.TaskModel.status.in_(_ACTIVE_STATUSES))
            .order_by(m.TaskModel.seq)
        )
        return [_task(r) for r in rows]

    async def list_for_user(self, user_id: UUID, limit: int = 50) -> list[Task]:
        rows = await self._s.scalars(
            select(m.TaskModel)
            .where(
                or_(
                    m.TaskModel.assignee_id == user_id,
                    m.TaskModel.status.in_(_ACTIVE_STATUSES),
                )
            )
            .order_by(m.TaskModel.seq.desc())
            .limit(max(1, min(limit, 100)))
        )
        return [_task(r) for r in rows]

    async def list_active_for_chat(self, telegram_chat_id: int) -> list[Task]:
        source_chat = aliased(m.TelegramChatModel)
        default_chat = aliased(m.TelegramChatModel)
        rows = await self._s.scalars(
            select(m.TaskModel)
            .outerjoin(
                m.ChatMessageModel,
                m.ChatMessageModel.id == m.TaskModel.source_message_id,
            )
            .outerjoin(source_chat, source_chat.id == m.ChatMessageModel.chat_id)
            .outerjoin(m.ProjectModel, m.ProjectModel.id == m.TaskModel.project_id)
            .outerjoin(default_chat, default_chat.id == m.ProjectModel.default_chat_id)
            .where(
                m.TaskModel.status.in_(_ACTIVE_STATUSES),
                or_(
                    source_chat.telegram_chat_id == telegram_chat_id,
                    and_(
                        m.TaskModel.source_message_id.is_(None),
                        default_chat.telegram_chat_id == telegram_chat_id,
                    ),
                ),
            )
            .order_by(m.TaskModel.seq)
        )
        return [_task(r) for r in rows]

    async def list_for_deadline_reminder(self, now: datetime, hours_before: int) -> list[Task]:
        from datetime import timedelta

        threshold = now + timedelta(hours=hours_before)
        rows = await self._s.scalars(
            select(m.TaskModel).where(
                m.TaskModel.deadline.is_not(None),
                m.TaskModel.status.not_in(_TERMINAL_STATUSES),
                m.TaskModel.deadline <= threshold,
            )
        )
        return [_task(r) for r in rows]

    async def list_stale(self, now: datetime, stale_hours: int) -> list[Task]:
        from datetime import timedelta

        threshold = now - timedelta(hours=stale_hours)
        reference = func.coalesce(
            m.TaskModel.last_status_update_at,
            m.TaskModel.updated_at,
            m.TaskModel.created_at,
        )
        rows = await self._s.scalars(
            select(m.TaskModel).where(
                m.TaskModel.status.in_(_ACTIVE_STATUSES),
                reference <= threshold,
            )
        )
        return [_task(r) for r in rows]

    async def count_completed_since(self, since: datetime) -> int:
        result = await self._s.scalar(
            select(func.count())
            .select_from(m.TaskModel)
            .where(
                m.TaskModel.status == TaskStatus.done.value,
                m.TaskModel.completed_at.is_not(None),
                m.TaskModel.completed_at >= since,
            )
        )
        return int(result or 0)

    async def list_completed_since(self, since: datetime) -> list[Task]:
        rows = await self._s.scalars(
            select(m.TaskModel)
            .where(
                m.TaskModel.status == TaskStatus.done.value,
                m.TaskModel.completed_at.is_not(None),
                m.TaskModel.completed_at >= since,
            )
            .order_by(m.TaskModel.seq)
        )
        return [_task(r) for r in rows]

    async def count_overdue(self, now: datetime) -> int:
        result = await self._s.scalar(
            select(func.count())
            .select_from(m.TaskModel)
            .where(
                m.TaskModel.deadline.is_not(None),
                m.TaskModel.deadline < now,
                m.TaskModel.status.in_(_ACTIVE_STATUSES),
            )
        )
        return int(result or 0)


class BoardCardRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, card: BoardCard) -> BoardCard:
        row = m.BoardCardModel(
            id=card.id,
            task_id=card.task_id,
            provider=card.provider.value,
            external_card_id=card.external_card_id,
            external_url=card.external_url,
            external_payload=card.external_payload,
        )
        self._s.add(row)
        await self._s.flush()
        return _board_card(row)

    async def get_by_task(self, task_id: UUID) -> BoardCard | None:
        row = await self._s.scalar(
            select(m.BoardCardModel).where(m.BoardCardModel.task_id == task_id)
        )
        return _board_card(row) if row else None

    async def update(self, card: BoardCard) -> BoardCard:
        row = await self._s.get(m.BoardCardModel, card.id)
        if row is None:
            raise ValueError(f"BoardCard {card.id} not found")
        row.external_url = card.external_url
        row.external_payload = card.external_payload
        await self._s.flush()
        await self._s.refresh(row)
        return _board_card(row)


class TranscriptRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, event: TranscriptEvent) -> TranscriptEvent:
        row = m.TranscriptEventModel(
            id=event.id,
            meeting_db_id=event.meeting_db_id,
            meeting_id=event.meeting_id,
            speaker_id=event.speaker_id,
            speaker_name=event.speaker_name,
            text=event.text,
            ts=event.ts,
            is_final=event.is_final,
            confidence=event.confidence,
            source=event.source,
            raw_json=event.raw_json,
        )
        self._s.add(row)
        await self._s.flush()
        event.created_at = row.created_at
        return event

    async def list_recent(self, limit: int = 20) -> list[TranscriptEvent]:
        rows = await self._s.scalars(
            select(m.TranscriptEventModel)
            .order_by(m.TranscriptEventModel.created_at.desc())
            .limit(max(1, min(limit, 100)))
        )
        return [_transcript_event(row) for row in rows]

    async def list_recent_for_user(self, user_id: UUID, limit: int = 20) -> list[TranscriptEvent]:
        rows = await self._s.scalars(
            select(m.TranscriptEventModel)
            .where(m.TranscriptEventModel.speaker_id == str(user_id))
            .order_by(m.TranscriptEventModel.created_at.desc())
            .limit(max(1, min(limit, 100)))
        )
        return [_transcript_event(row) for row in rows]

    async def list_recent_for_meeting(
        self, meeting_db_id: UUID, limit: int = 8
    ) -> list[TranscriptEvent]:
        rows = await self._s.scalars(
            select(m.TranscriptEventModel)
            .where(m.TranscriptEventModel.meeting_db_id == meeting_db_id)
            .where(m.TranscriptEventModel.is_final.is_(True))
            .order_by(m.TranscriptEventModel.created_at.desc())
            .limit(max(1, min(limit, 20)))
        )
        return list(reversed([_transcript_event(row) for row in rows]))


class DebugRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def counts(self) -> dict[str, int]:
        models = {
            "users": m.UserModel,
            "telegram_chats": m.TelegramChatModel,
            "meetings": m.MeetingModel,
            "transcripts": m.TranscriptEventModel,
            "task_proposals": m.TaskProposalModel,
            "tasks": m.TaskModel,
            "board_cards": m.BoardCardModel,
        }
        return {
            name: int(await self._s.scalar(select(func.count()).select_from(model)) or 0)
            for name, model in models.items()
        }

    async def reset_demo(self) -> dict[str, int]:
        rows = await self._s.scalars(select(m.MeetingModel))
        meeting_ids = [row.id for row in rows if (row.metadata_json or {}).get("demo")]
        if not meeting_ids:
            return {"meetings": 0, "transcripts": 0}
        transcript_count = int(
            await self._s.scalar(
                select(func.count())
                .select_from(m.TranscriptEventModel)
                .where(m.TranscriptEventModel.meeting_db_id.in_(meeting_ids))
            )
            or 0
        )
        await self._s.execute(
            delete(m.TranscriptEventModel).where(
                m.TranscriptEventModel.meeting_db_id.in_(meeting_ids)
            )
        )
        await self._s.execute(delete(m.MeetingModel).where(m.MeetingModel.id.in_(meeting_ids)))
        return {
            "meetings": len(meeting_ids),
            "transcripts": transcript_count,
        }


class ReminderRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, log: ReminderLog) -> ReminderLog:
        row = m.ReminderLogModel(
            id=log.id,
            task_id=log.task_id,
            kind=log.kind.value,
            recipient_telegram_user_id=log.recipient_telegram_user_id,
            telegram_chat_id=log.telegram_chat_id,
            payload=log.payload,
        )
        self._s.add(row)
        await self._s.flush()
        log.sent_at = row.sent_at
        return log

    async def exists(self, task_id: UUID, kind: ReminderKind) -> bool:
        result = await self._s.scalar(
            select(func.count())
            .select_from(m.ReminderLogModel)
            .where(
                m.ReminderLogModel.task_id == task_id,
                m.ReminderLogModel.kind == kind.value,
            )
        )
        return bool(result)

    async def last_sent_at(self, task_id: UUID, kind: ReminderKind) -> datetime | None:
        return await self._s.scalar(
            select(func.max(m.ReminderLogModel.sent_at)).where(
                m.ReminderLogModel.task_id == task_id,
                m.ReminderLogModel.kind == kind.value,
            )
        )

    async def count_for_user_since(self, recipient_telegram_user_id: int, since: datetime) -> int:
        result = await self._s.scalar(
            select(func.count())
            .select_from(m.ReminderLogModel)
            .where(
                m.ReminderLogModel.recipient_telegram_user_id == recipient_telegram_user_id,
                m.ReminderLogModel.sent_at >= since,
            )
        )
        return int(result or 0)

    async def last_sent_to_user(self, recipient_telegram_user_id: int) -> datetime | None:
        return await self._s.scalar(
            select(func.max(m.ReminderLogModel.sent_at)).where(
                m.ReminderLogModel.recipient_telegram_user_id == recipient_telegram_user_id,
            )
        )


class DigestRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, log: DigestLog) -> DigestLog:
        row = m.DigestLogModel(
            id=log.id,
            telegram_user_id=log.telegram_user_id,
            telegram_chat_id=log.telegram_chat_id,
            payload=log.payload,
        )
        self._s.add(row)
        await self._s.flush()
        log.sent_at = row.sent_at
        return log

    async def sent_today(self, chat_id: int, day: datetime) -> bool:
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._s.scalar(
            select(func.count())
            .select_from(m.DigestLogModel)
            .where(
                m.DigestLogModel.telegram_chat_id == chat_id,
                m.DigestLogModel.sent_at >= start,
            )
        )
        return bool(result)

    async def sent_today_for_user(self, telegram_user_id: int, day: datetime) -> bool:
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._s.scalar(
            select(func.count())
            .select_from(m.DigestLogModel)
            .where(
                m.DigestLogModel.telegram_user_id == telegram_user_id,
                m.DigestLogModel.sent_at >= start,
            )
        )
        return bool(result)


class AuditRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, log: AuditLog) -> AuditLog:
        row = m.AuditLogModel(
            id=log.id,
            actor_type=log.actor_type,
            actor_id=log.actor_id,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            payload=log.payload,
        )
        self._s.add(row)
        await self._s.flush()
        log.created_at = row.created_at
        return log


class GamificationRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add_event_once(self, event: UserXpEvent) -> UserXpEvent | None:
        idempotency_key = event.metadata.get("idempotency_key")
        if idempotency_key:
            existing = await self._s.scalar(
                select(m.UserXpEventModel).where(
                    m.UserXpEventModel.user_id == event.user_id,
                    m.UserXpEventModel.kind == event.kind.value,
                    m.UserXpEventModel.metadata_json["idempotency_key"].as_string()
                    == str(idempotency_key),
                )
            )
            if existing is not None:
                return None

        row = m.UserXpEventModel(
            id=event.id,
            user_id=event.user_id,
            workspace_id=event.workspace_id,
            task_id=event.task_id,
            meeting_id=event.meeting_id,
            kind=event.kind.value,
            points=event.points,
            reason=event.reason,
            metadata_json=event.metadata,
        )
        self._s.add(row)
        await self._s.flush()

        total_row = await self._find_total_row(event.user_id, event.workspace_id)
        if total_row is None:
            total_row = m.UserXpTotalModel(
                id=uuid4(),
                user_id=event.user_id,
                workspace_id=event.workspace_id,
                points_total=0,
                level=1,
            )
            self._s.add(total_row)
            await self._s.flush()
        total_row.points_total += event.points
        total_row.level = max(1, (total_row.points_total // 100) + 1)
        await self._s.flush()
        await self._s.refresh(row)
        return _xp_event(row)

    async def get_total(self, user_id: UUID, workspace_id: UUID | None = None) -> UserXpTotal:
        row = await self._find_total_row(user_id, workspace_id)
        if row is None:
            row = m.UserXpTotalModel(
                id=uuid4(),
                user_id=user_id,
                workspace_id=workspace_id,
                points_total=0,
                level=1,
            )
            self._s.add(row)
            await self._s.flush()
            await self._s.refresh(row)
        return _xp_total(row)

    async def list_recent(self, user_id: UUID, limit: int = 20) -> list[UserXpEvent]:
        rows = await self._s.scalars(
            select(m.UserXpEventModel)
            .where(m.UserXpEventModel.user_id == user_id)
            .order_by(m.UserXpEventModel.created_at.desc())
            .limit(max(1, min(limit, 100)))
        )
        return [_xp_event(row) for row in rows]

    async def _find_total_row(
        self, user_id: UUID, workspace_id: UUID | None
    ) -> m.UserXpTotalModel | None:
        statement = select(m.UserXpTotalModel).where(m.UserXpTotalModel.user_id == user_id)
        if workspace_id is None:
            statement = statement.where(m.UserXpTotalModel.workspace_id.is_(None))
        else:
            statement = statement.where(m.UserXpTotalModel.workspace_id == workspace_id)
        return await self._s.scalar(statement)


# --------------------------------------------------------------------------- #
# UnitOfWork
# --------------------------------------------------------------------------- #
class SqlAlchemyUnitOfWork:
    """Открывает сессию и агрегирует репозитории. Транзакция фиксируется commit()."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.users = UserRepositoryImpl(session)
        self.devices = DeviceRepositoryImpl(session)
        self.client_sessions = ClientSessionRepositoryImpl(session)
        self.projects = ProjectRepositoryImpl(session)
        self.chats = ChatRepositoryImpl(session)
        self.messages = MessageRepositoryImpl(session)
        self.meetings = MeetingRepositoryImpl(session)
        self.meeting_participants = MeetingParticipantRepositoryImpl(session)
        self.proposals = ProposalRepositoryImpl(session)
        self.confirmations = ConfirmationRepositoryImpl(session)
        self.tasks = TaskRepositoryImpl(session)
        self.board_cards = BoardCardRepositoryImpl(session)
        self.transcripts = TranscriptRepositoryImpl(session)
        self.debug = DebugRepositoryImpl(session)
        self.reminders = ReminderRepositoryImpl(session)
        self.digests = DigestRepositoryImpl(session)
        self.audit = AuditRepositoryImpl(session)
        self.gamification = GamificationRepositoryImpl(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._session.rollback()
        await self._session.close()
