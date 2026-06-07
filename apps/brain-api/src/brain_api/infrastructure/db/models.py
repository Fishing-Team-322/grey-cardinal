"""SQLAlchemy 2.0 ORM-модели brain-api.

Типы выбраны переносимыми: на PostgreSQL — native UUID / JSONB / TIMESTAMPTZ,
на SQLite (тесты) — совместимые аналоги через `.with_variant`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid

# JSONB на PostgreSQL, обычный JSON на остальных диалектах.
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = _uuid_pk()
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Web account fields (migration 0004_user_accounts)
    email: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True, index=True)
    login: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    photo_data_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="member")


class TelegramLinkCodeModel(Base):
    __tablename__ = "telegram_link_codes"

    id: Mapped[UUID] = _uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TelegramTeamBindCodeModel(Base):
    __tablename__ = "telegram_team_bind_codes"

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceLinkCodeModel(Base):
    """One-time, time-limited code that pairs a desktop/tray agent to a user.

    Mirrors TelegramLinkCodeModel: the user generates a code in their cabinet,
    types it into the agent, and the agent exchanges it (POST /api/agents/register)
    for a ClientSession token bound to that user. Replaces the demo AgentsStore.
    """

    __tablename__ = "device_link_codes"

    id: Mapped[UUID] = _uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceModel(TimestampMixin, Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = _uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    device_name: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    app_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClientSessionModel(TimestampMixin, Base):
    __tablename__ = "client_sessions"

    id: Mapped[UUID] = _uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    session_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectModel(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_chat_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class TelegramChatModel(TimestampMixin, Base):
    __tablename__ = "telegram_chats"

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    telegram_chat_id: Mapped[int] = mapped_column(
        "tg_chat_id", BigInteger, unique=True, nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    linked_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    task_confirmation_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="1"
    )


class ChatMessageModel(TimestampMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("chat_id", "telegram_message_id", name="uq_chat_message"),)

    id: Mapped[UUID] = _uuid_pk()
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[UUID] = mapped_column(ForeignKey("telegram_chats.id"), nullable=False)
    sender_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sender_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reply_to_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reply_to_sender_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reply_to_sender_telegram_user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    reply_to_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_thread_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)


class TaskProposalModel(TimestampMixin, Base):
    __tablename__ = "task_proposals"

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("chat_messages.id"), nullable=True
    )
    source_transcript_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_payload: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    similar_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)


class ConfirmationModel(TimestampMixin, Base):
    __tablename__ = "confirmations"

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    proposal_id: Mapped[UUID] = mapped_column(ForeignKey("task_proposals.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskModel(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("team_id", "public_id", name="uq_task_team_public_id"),
        UniqueConstraint("team_id", "seq", name="uq_task_team_seq"),
    )

    id: Mapped[UUID] = _uuid_pk()
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    public_id: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assignee_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    source_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("chat_messages.id"), nullable=True
    )
    created_from_proposal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("task_proposals.id"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_update_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BoardCardModel(TimestampMixin, Base):
    __tablename__ = "board_cards"

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_card_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)


class TranscriptEventModel(Base):
    # Транскрипт-события неизменяемы (append-only): только created_at, без
    # updated_at — это совпадает с миграцией 0001_initial_v2 (см. таблицу
    # transcript_events) и не ломает INSERT ... RETURNING на PostgreSQL.
    __tablename__ = "transcript_events"

    id: Mapped[UUID] = _uuid_pk()
    meeting_db_id: Mapped[UUID | None] = mapped_column(ForeignKey("meetings.id"), nullable=True)
    meeting_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    speaker_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    speaker_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="audio_worker")
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MeetingModel(TimestampMixin, Base):
    __tablename__ = "meetings"

    id: Mapped[UUID] = _uuid_pk()
    seq: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    public_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    telegram_chat_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("telegram_chats.id"), nullable=True
    )
    external_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    poll_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)


class MeetingParticipantModel(TimestampMixin, Base):
    __tablename__ = "meeting_participants"
    __table_args__ = (
        UniqueConstraint("meeting_id", "user_id", name="uq_meeting_participant_user"),
    )

    id: Mapped[UUID] = _uuid_pk()
    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    client_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("client_sessions.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)


class MeetingRsvpModel(TimestampMixin, Base):
    __tablename__ = "meeting_rsvp"
    __table_args__ = (UniqueConstraint("meeting_id", "user_id", name="uq_meeting_rsvp_user"),)

    id: Mapped[UUID] = _uuid_pk()
    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)


class ReminderLogModel(Base):
    __tablename__ = "reminder_logs"

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recipient_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)


class DigestLogModel(Base):
    __tablename__ = "digest_logs"

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    date: Mapped[Any | None] = mapped_column(Date, nullable=True)
    timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = _uuid_pk()
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserXpEventModel(Base):
    __tablename__ = "user_xp_events"

    id: Mapped[UUID] = _uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    meeting_id: Mapped[UUID | None] = mapped_column(ForeignKey("meetings.id"), nullable=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserXpTotalModel(Base):
    __tablename__ = "user_xp_totals"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id", name="uq_user_xp_total_scope"),)

    id: Mapped[UUID] = _uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    points_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --- Grey Cardinal v2 production domain ------------------------------------


class CompanyModel(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class CompanyAdminModel(Base):
    __tablename__ = "company_admins"
    __table_args__ = (
        CheckConstraint("role in ('director')", name="ck_company_admin_role"),
        UniqueConstraint("company_id", "user_id", name="uq_company_admin_user"),
    )

    id: Mapped[UUID] = _uuid_pk()
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LLMSettingsModel(TimestampMixin, Base):
    __tablename__ = "llm_settings"
    __table_args__ = (
        CheckConstraint("provider in ('local','external_api')", name="ck_llm_settings_provider"),
    )

    id: Mapped[UUID] = _uuid_pk()
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    strict_json: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")


class TeamModel(TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        CheckConstraint("board_provider in ('yougile','mock')", name="ck_team_board_provider"),
    )

    id: Mapped[UUID] = _uuid_pk()
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    board_provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="yougile")
    board_credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    board_config: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    llm_settings_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("llm_settings.id"), nullable=True
    )


class TeamMemberModel(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        CheckConstraint("role in ('manager','employee')", name="ck_team_member_role"),
        UniqueConstraint("team_id", "user_id", name="uq_team_member_user"),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    invited_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserAliasModel(TimestampMixin, Base):
    __tablename__ = "user_aliases"
    __table_args__ = (
        UniqueConstraint("team_id", "normalized_alias", name="uq_user_alias_team_normalized"),
        Index("ix_user_alias_team_user", "team_id", "user_id"),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_alias: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="1")


class AIInboxItemModel(TimestampMixin, Base):
    __tablename__ = "ai_inbox_items"
    __table_args__ = (
        Index("ix_ai_inbox_team_status_created", "team_id", "status", "created_at"),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    source_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("chat_messages.id"), nullable=True
    )
    kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    identity_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    duplicate_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )
    item_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    proposed_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")


class YouGileBoardModel(Base):
    __tablename__ = "yougile_boards"
    __table_args__ = (
        UniqueConstraint("team_id", "external_id", name="uq_yougile_board_team_external"),
        Index("ix_yougile_board_selected", "team_id", "is_selected"),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    connection_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("yougile_connections.id"), nullable=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("yougile_projects.id"), nullable=True
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class YouGileColumnModel(Base):
    __tablename__ = "yougile_columns"
    __table_args__ = (
        UniqueConstraint("board_id", "external_id", name="uq_yougile_column_board_external"),
        Index("ix_yougile_column_status", "board_id", "mapped_status"),
    )

    id: Mapped[UUID] = _uuid_pk()
    board_id: Mapped[UUID] = mapped_column(ForeignKey("yougile_boards.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    mapped_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExternalTaskLinkModel(TimestampMixin, Base):
    __tablename__ = "external_task_links"
    __table_args__ = (
        UniqueConstraint("provider", "external_task_id", name="uq_external_task_provider_id"),
        UniqueConstraint("team_id", "task_id", "provider", name="uq_external_task_local"),
        Index("ix_external_task_team_sync", "team_id", "sync_status"),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_board_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_column_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_task_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="local_only")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)


class SyncEventModel(Base):
    __tablename__ = "sync_events"
    __table_args__ = (Index("ix_sync_event_team_created", "team_id", "created_at"),)

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    link_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("external_task_links.id"), nullable=True
    )
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InviteModel(Base):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint("scope in ('company','team')", name="ck_invite_scope"),
        CheckConstraint("role in ('director','manager','employee')", name="ck_invite_role"),
    )

    id: Mapped[UUID] = _uuid_pk()
    token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── YouGile integration (migration 0004) ──────────────────────────────────────


class YouGileMappingModel(Base):
    """Bidirectional mapping between our entities and YouGile entities.

    UNIQUE(team_id, entity_type, yougile_id) makes discovery idempotent (upsert).
    local_id is NULL for entities that exist only in YouGile (not mirrored yet).
    payload keeps the last known YouGile snapshot for diffing.
    """

    __tablename__ = "yougile_mappings"
    __table_args__ = (
        CheckConstraint(
            "entity_type in ('project','board','column','task','user')",
            name="ck_yougile_mapping_entity",
        ),
        UniqueConstraint("team_id", "entity_type", "yougile_id", name="uq_yougile_mapping"),
        Index("ix_yougile_mapping_local", "team_id", "entity_type", "local_id"),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    local_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    yougile_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class YouGileSyncLogModel(Base):
    """Append-only audit of inbound (webhook) and outbound (our push) sync events."""

    __tablename__ = "yougile_sync_log"
    __table_args__ = (
        CheckConstraint(
            "direction in ('inbound','outbound')", name="ck_yougile_synclog_direction"
        ),
        Index("ix_yougile_synclog_team_created", "team_id", "created_at"),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    yougile_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    event: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class YouGileConnectionModel(TimestampMixin, Base):
    # Single source of truth: merges the two previously-duplicated declarations
    # (both were used by code) into the union of columns the migrations create
    # (0007 _create_yougile_connections + alters) and the routes/discovery write.
    __tablename__ = "yougile_connections"
    __table_args__ = (UniqueConstraint("team_id", name="uq_yougile_connection_team"),)

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="yougile")
    external_company_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="connected")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class YouGileWorkspaceModel(Base):
    __tablename__ = "yougile_workspaces"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_id", name="uq_yougile_workspace_external"),
    )

    id: Mapped[UUID] = _uuid_pk()
    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("yougile_connections.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class YouGileProjectModel(Base):
    __tablename__ = "yougile_projects"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_id", name="uq_yougile_project_external"),
    )

    id: Mapped[UUID] = _uuid_pk()
    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("yougile_connections.id"), nullable=False
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("yougile_workspaces.id"), nullable=True
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# Keep the historical spelling as an import-compatible alias to the single mapped class.
AiInboxItemModel = AIInboxItemModel


class AgentRecommendationModel(TimestampMixin, Base):
    __tablename__ = "agent_recommendations"

    id: Mapped[UUID] = _uuid_pk()
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)


class TelegramTopicBindingModel(TimestampMixin, Base):
    __tablename__ = "telegram_topic_bindings"
    __table_args__ = (
        UniqueConstraint("telegram_chat_id", "message_thread_id", name="uq_telegram_topic_binding"),
    )

    id: Mapped[UUID] = _uuid_pk()
    telegram_chat_id: Mapped[UUID] = mapped_column(ForeignKey("telegram_chats.id"), nullable=False)
    message_thread_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    board_id: Mapped[UUID | None] = mapped_column(ForeignKey("yougile_boards.id"), nullable=True)
    source_name: Mapped[str | None] = mapped_column(Text, nullable=True)


V2TelegramChatModel = TelegramChatModel
V2TaskModel = TaskModel
V2TaskProposalModel = TaskProposalModel
V2ConfirmationModel = ConfirmationModel
V2MeetingModel = MeetingModel


class DailySyncSessionModel(TimestampMixin, Base):
    __tablename__ = "daily_sync_sessions"
    __table_args__ = (
        CheckConstraint("status in ('open','closed')", name="ck_daily_sync_status"),
        UniqueConstraint("team_id", "date", name="uq_daily_sync_team_date"),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    date: Mapped[Any] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DailySyncReportModel(Base):
    __tablename__ = "daily_sync_reports"
    __table_args__ = (
        CheckConstraint(
            "detected_status in ('done','in_progress','blocked','unknown')",
            name="ck_daily_sync_report_status",
        ),
    )

    id: Mapped[UUID] = _uuid_pk()
    sync_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("daily_sync_sessions.id"), nullable=False
    )
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    telegram_message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    detected_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AbsencePeriodModel(TimestampMixin, Base):
    __tablename__ = "absence_periods"
    __table_args__ = (
        CheckConstraint("status in ('active','expired','cancelled')", name="ck_absence_status"),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    delegate_to_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


V2BoardCardModel = BoardCardModel
V2ReminderLogModel = ReminderLogModel
V2DigestLogModel = DigestLogModel


class GamificationEventModel(Base):
    __tablename__ = "gamification_events"

    id: Mapped[UUID] = _uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    xp_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Yandex Telemost integration (OAuth, tenant-scoped) ────────────────────────


class YandexTelemostIntegrationModel(TimestampMixin, Base):
    """Per-team Yandex Telemost OAuth connection.

    Tokens are stored ONLY encrypted (Fernet via SecretCipher). Never serialized
    to API responses or logs. One row per team (the team = workspace tenant).
    """

    __tablename__ = "yandex_telemost_integrations"
    __table_args__ = (
        UniqueConstraint("team_id", name="uq_yandex_telemost_team"),
        CheckConstraint(
            "status in ('connected','expired','disconnected','error')",
            name="ck_yandex_telemost_status",
        ),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="yandex_telemost")
    yandex_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    refresh_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="disconnected")
    # UI/behaviour settings: enable_meeting_agent_auto_join, send_ai_recording_notice_to_chat,
    # default_title_template.
    settings: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class YandexOAuthStateModel(Base):
    """One-time CSRF state for the Yandex OAuth dance, bound to user+team."""

    __tablename__ = "yandex_oauth_states"

    id: Mapped[UUID] = _uuid_pk()
    state: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="yandex_telemost")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MeetingAgentJoinJobModel(TimestampMixin, Base):
    """Queue stub for the meeting recording agent joining a Telemost room.

    MVP does NOT auto-join (no hidden recording). This row records intent so a
    future worker can pick it up; until then it stays 'pending'.
    """

    __tablename__ = "meeting_agent_join_jobs"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','queued','failed','completed')",
            name="ck_meeting_agent_join_status",
        ),
    )

    id: Mapped[UUID] = _uuid_pk()
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="yandex_telemost")
    meeting_url: Mapped[str] = mapped_column(Text, nullable=False)
    conference_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    meeting_id: Mapped[UUID | None] = mapped_column(ForeignKey("meetings.id"), nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
