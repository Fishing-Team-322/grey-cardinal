"""Конкретные репозитории (SQLAlchemy) и UnitOfWork.

Репозитории маппят ORM-модели в доменные сущности и обратно, чтобы домен и
use cases не зависели от SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.domain.entities import (
    AuditLog,
    BoardCard,
    ChatMessage,
    Confirmation,
    DigestLog,
    Project,
    ReminderLog,
    Task,
    TaskProposal,
    TelegramChat,
    TranscriptEvent,
    User,
)
from brain_api.domain.enums import (
    BoardProvider,
    ConfirmationStatus,
    ReminderKind,
    TaskPriority,
    TaskSource,
    TaskStatus,
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
        return _user(row)

    async def get(self, user_id: UUID) -> User | None:
        row = await self._s.get(m.UserModel, user_id)
        return _user(row) if row else None

    async def list_known(self, limit: int = 50) -> list[User]:
        rows = await self._s.scalars(select(m.UserModel).limit(limit))
        return [_user(r) for r in rows]


class ProjectRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def ensure_default(self) -> Project:
        row = await self._s.scalar(select(m.ProjectModel).order_by(m.ProjectModel.created_at))
        if row is None:
            row = m.ProjectModel(id=uuid4(), name="Default")
            self._s.add(row)
            await self._s.flush()
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

    async def get(self, chat_id: UUID) -> TelegramChat | None:
        row = await self._s.get(m.TelegramChatModel, chat_id)
        return _chat(row) if row else None


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
            select(m.TaskProposalModel).where(
                m.TaskProposalModel.source_message_id == message_id
            )
        )
        return _proposal(row) if row else None


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
        return _confirmation(row)


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
        row = await self._s.scalar(
            select(m.TaskModel).where(m.TaskModel.public_id == public_id)
        )
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
        return _task(row)

    async def list_active(self) -> list[Task]:
        rows = await self._s.scalars(
            select(m.TaskModel)
            .where(m.TaskModel.status.in_(_ACTIVE_STATUSES))
            .order_by(m.TaskModel.seq)
        )
        return [_task(r) for r in rows]

    async def list_for_deadline_reminder(
        self, now: datetime, hours_before: int
    ) -> list[Task]:
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
        return _board_card(row)


class TranscriptRepositoryImpl:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, event: TranscriptEvent) -> TranscriptEvent:
        row = m.TranscriptEventModel(
            id=event.id,
            meeting_id=event.meeting_id,
            speaker_id=event.speaker_id,
            speaker_name=event.speaker_name,
            text=event.text,
            ts=event.ts,
            is_final=event.is_final,
            raw_json=event.raw_json,
        )
        self._s.add(row)
        await self._s.flush()
        event.created_at = row.created_at
        return event


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


# --------------------------------------------------------------------------- #
# UnitOfWork
# --------------------------------------------------------------------------- #
class SqlAlchemyUnitOfWork:
    """Открывает сессию и агрегирует репозитории. Транзакция фиксируется commit()."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.users = UserRepositoryImpl(session)
        self.projects = ProjectRepositoryImpl(session)
        self.chats = ChatRepositoryImpl(session)
        self.messages = MessageRepositoryImpl(session)
        self.proposals = ProposalRepositoryImpl(session)
        self.confirmations = ConfirmationRepositoryImpl(session)
        self.tasks = TaskRepositoryImpl(session)
        self.board_cards = BoardCardRepositoryImpl(session)
        self.transcripts = TranscriptRepositoryImpl(session)
        self.reminders = ReminderRepositoryImpl(session)
        self.digests = DigestRepositoryImpl(session)
        self.audit = AuditRepositoryImpl(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._session.rollback()
        await self._session.close()
