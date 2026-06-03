"""Порты application-слоя.

Use cases зависят только от этих абстракций (Protocol), а не от конкретных
реализаций в infrastructure. Это позволяет подменять LLM, доску, Telegram и
хранилище без изменения бизнес-логики.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

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
from brain_api.domain.enums import ReminderKind, TaskStatus
from grey_cardinal_contracts import (
    BoardCardResult,
    KnownUser,
    TaskExtractionResult,
    WebsocketEvent,
)


# --------------------------------------------------------------------------- #
# Внешние шлюзы
# --------------------------------------------------------------------------- #
@runtime_checkable
class TaskExtractor(Protocol):
    async def extract_task(
        self,
        text: str,
        now: datetime,
        timezone: str,
        known_users: list[KnownUser],
    ) -> TaskExtractionResult: ...


@runtime_checkable
class BoardGateway(Protocol):
    async def create_card(self, task: Task) -> BoardCardResult: ...
    async def move_card(self, external_card_id: str, status: TaskStatus) -> None: ...
    async def close_card(self, external_card_id: str) -> None: ...
    async def add_comment(self, external_card_id: str, text: str) -> None: ...


@runtime_checkable
class TelegramGateway(Protocol):
    """brain-api -> telegram-bot (для reminders/digests)."""

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> int | None: ...


@runtime_checkable
class EventPublisher(Protocol):
    """Публикация websocket-событий для dashboard."""

    async def publish(self, event: WebsocketEvent) -> None: ...


# --------------------------------------------------------------------------- #
# Репозитории
# --------------------------------------------------------------------------- #
class UserRepository(Protocol):
    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None: ...
    async def upsert_from_telegram(
        self, telegram_user_id: int, username: str | None, display_name: str
    ) -> User: ...
    async def upsert_desktop_user(
        self, display_name: str, telegram_username: str | None = None
    ) -> User: ...
    async def get(self, user_id: UUID) -> User | None: ...
    async def get_by_display_name(self, display_name: str) -> User | None: ...
    async def list_known(self, limit: int = 50) -> list[User]: ...


class DeviceRepository(Protocol):
    async def get(self, device_id: UUID) -> Device | None: ...
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
    ) -> Device: ...
    async def touch(self, device_id: UUID, now: datetime) -> Device | None: ...


class ClientSessionRepository(Protocol):
    async def get(self, session_id: UUID) -> ClientSession | None: ...
    async def start(
        self,
        *,
        user_id: UUID,
        device_id: UUID | None,
        workspace_id: UUID | None,
        now: datetime,
        expires_at: datetime | None = None,
    ) -> ClientSession: ...
    async def touch(self, session_id: UUID, now: datetime) -> ClientSession | None: ...


class ProjectRepository(Protocol):
    async def ensure_default(self, name: str = "Hackathon Team") -> Project: ...
    async def set_default_chat(self, project_id: UUID, chat_id: UUID) -> Project: ...


class ChatRepository(Protocol):
    async def upsert(
        self,
        telegram_chat_id: int,
        chat_type: str,
        title: str | None,
        project_id: UUID | None,
    ) -> TelegramChat: ...
    async def get_by_telegram_id(self, telegram_chat_id: int) -> TelegramChat | None: ...
    async def get(self, chat_id: UUID) -> TelegramChat | None: ...
    async def list_for_project(self, project_id: UUID) -> list[TelegramChat]: ...


class MeetingRepository(Protocol):
    async def add(self, meeting: Meeting) -> Meeting: ...
    async def get(self, meeting_id: UUID) -> Meeting | None: ...
    async def get_by_public_id(self, public_id: str) -> Meeting | None: ...
    async def get_active_for_chat(self, telegram_chat_id: int | None) -> Meeting | None: ...
    async def list_recent(self, limit: int = 20) -> list[Meeting]: ...
    async def next_sequence(self) -> int: ...
    async def update(self, meeting: Meeting) -> Meeting: ...
    async def count_transcripts(self, meeting_id: UUID) -> int: ...
    async def count_proposals(self, meeting_id: UUID) -> int: ...


class MeetingParticipantRepository(Protocol):
    async def join(
        self,
        *,
        meeting_id: UUID,
        user_id: UUID,
        device_id: UUID | None,
        client_session_id: UUID | None,
        now: datetime,
        metadata: dict | None = None,
    ) -> MeetingParticipant: ...
    async def leave(
        self, meeting_id: UUID, user_id: UUID, now: datetime
    ) -> MeetingParticipant | None: ...
    async def touch_active_for_session(
        self, client_session_id: UUID, now: datetime, meeting_id: UUID | None = None
    ) -> MeetingParticipant | None: ...
    async def list_for_meeting(self, meeting_id: UUID) -> list[MeetingParticipant]: ...


class MessageRepository(Protocol):
    async def get_by_tg(
        self, chat_id: UUID, telegram_message_id: int
    ) -> ChatMessage | None: ...
    async def add(self, message: ChatMessage) -> ChatMessage: ...


class ProposalRepository(Protocol):
    async def add(self, proposal: TaskProposal) -> TaskProposal: ...
    async def get(self, proposal_id: UUID) -> TaskProposal | None: ...
    async def get_by_source_message(self, message_id: UUID) -> TaskProposal | None: ...
    async def list_pending_for_user(self, user_id: UUID, limit: int = 20) -> list[TaskProposal]: ...


class ConfirmationRepository(Protocol):
    async def add(self, confirmation: Confirmation) -> Confirmation: ...
    async def get(self, confirmation_id: UUID) -> Confirmation | None: ...
    async def update(self, confirmation: Confirmation) -> Confirmation: ...
    async def get_pending_for_proposal(self, proposal_id: UUID) -> Confirmation | None: ...


class TaskRepository(Protocol):
    async def add(self, task: Task) -> Task: ...
    async def get(self, task_id: UUID) -> Task | None: ...
    async def get_by_public_id(self, public_id: str) -> Task | None: ...
    async def next_sequence(self) -> int: ...
    async def update(self, task: Task) -> Task: ...
    async def list_active(self) -> list[Task]: ...
    async def list_for_user(self, user_id: UUID, limit: int = 50) -> list[Task]: ...
    async def list_active_for_chat(self, telegram_chat_id: int) -> list[Task]: ...
    async def list_for_deadline_reminder(
        self, now: datetime, hours_before: int
    ) -> list[Task]: ...
    async def list_stale(self, now: datetime, stale_hours: int) -> list[Task]: ...
    async def count_completed_since(self, since: datetime) -> int: ...
    async def count_overdue(self, now: datetime) -> int: ...


class BoardCardRepository(Protocol):
    async def add(self, card: BoardCard) -> BoardCard: ...
    async def get_by_task(self, task_id: UUID) -> BoardCard | None: ...
    async def update(self, card: BoardCard) -> BoardCard: ...


class TranscriptRepository(Protocol):
    async def add(self, event: TranscriptEvent) -> TranscriptEvent: ...
    async def list_recent(self, limit: int = 20) -> list[TranscriptEvent]: ...
    async def list_recent_for_user(self, user_id: UUID, limit: int = 20) -> list[TranscriptEvent]: ...


class DebugRepository(Protocol):
    async def counts(self) -> dict[str, int]: ...
    async def reset_demo(self) -> dict[str, int]: ...


class ReminderRepository(Protocol):
    async def add(self, log: ReminderLog) -> ReminderLog: ...
    async def exists(self, task_id: UUID, kind: ReminderKind) -> bool: ...
    async def last_sent_at(self, task_id: UUID, kind: ReminderKind) -> datetime | None: ...


class DigestRepository(Protocol):
    async def add(self, log: DigestLog) -> DigestLog: ...
    async def sent_today(self, chat_id: int, day: datetime) -> bool: ...


class AuditRepository(Protocol):
    async def add(self, log: AuditLog) -> AuditLog: ...


class GamificationRepository(Protocol):
    async def add_event_once(self, event: UserXpEvent) -> UserXpEvent | None: ...
    async def get_total(self, user_id: UUID, workspace_id: UUID | None = None) -> UserXpTotal: ...
    async def list_recent(self, user_id: UUID, limit: int = 20) -> list[UserXpEvent]: ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Агрегирует репозитории и управляет транзакцией.

    Используется как async-контекст: `async with uow: ...; await uow.commit()`.
    """

    users: UserRepository
    devices: DeviceRepository
    client_sessions: ClientSessionRepository
    projects: ProjectRepository
    chats: ChatRepository
    messages: MessageRepository
    meetings: MeetingRepository
    meeting_participants: MeetingParticipantRepository
    proposals: ProposalRepository
    confirmations: ConfirmationRepository
    tasks: TaskRepository
    board_cards: BoardCardRepository
    transcripts: TranscriptRepository
    debug: DebugRepository
    reminders: ReminderRepository
    digests: DigestRepository
    audit: AuditRepository
    gamification: GamificationRepository

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def __aenter__(self) -> UnitOfWork: ...
    async def __aexit__(self, *exc: object) -> None: ...
