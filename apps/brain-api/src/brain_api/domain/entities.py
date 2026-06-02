"""Доменные сущности — чистые dataclass'ы.

ORM-модели (SQLAlchemy) живут отдельно в infrastructure/db/models.py; репозитории
маппят их в эти сущности. Так домен не зависит от способа хранения.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

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


@dataclass
class User:
    id: UUID
    display_name: str
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Device:
    id: UUID
    user_id: UUID
    device_name: str
    platform: str
    workspace_id: UUID | None = None
    app_version: str | None = None
    device_fingerprint: str | None = None
    last_seen_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ClientSession:
    id: UUID
    user_id: UUID
    status: ClientSessionStatus
    started_at: datetime
    device_id: UUID | None = None
    workspace_id: UUID | None = None
    session_token_hash: str | None = None
    last_seen_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Project:
    id: UUID
    name: str
    default_chat_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class TelegramChat:
    id: UUID
    telegram_chat_id: int
    type: str
    title: str | None = None
    project_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ChatMessage:
    id: UUID
    telegram_message_id: int
    chat_id: UUID
    text: str
    sender_id: UUID | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class TranscriptEvent:
    id: UUID
    text: str
    ts: datetime
    is_final: bool
    meeting_id: str | None = None
    meeting_db_id: UUID | None = None
    speaker_id: str | None = None
    speaker_name: str | None = None
    confidence: float | None = None
    source: str = "audio_worker"
    raw_json: dict[str, Any] | None = None
    created_at: datetime | None = None


@dataclass
class Meeting:
    id: UUID
    public_id: str
    status: MeetingStatus
    started_at: datetime
    project_id: UUID | None = None
    telegram_chat_id: UUID | None = None
    external_source: str | None = None
    title: str | None = None
    stopped_at: datetime | None = None
    created_by_user_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class MeetingParticipant:
    id: UUID
    meeting_id: UUID
    user_id: UUID
    status: MeetingParticipantStatus
    joined_at: datetime
    device_id: UUID | None = None
    client_session_id: UUID | None = None
    left_at: datetime | None = None
    last_seen_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class TaskProposal:
    id: UUID
    source: TaskSource
    title: str
    priority: TaskPriority
    confidence: float
    raw_text: str
    extractor_payload: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    source_message_id: UUID | None = None
    source_transcript_id: UUID | None = None
    assignee_text: str | None = None
    assignee_id: UUID | None = None
    deadline: datetime | None = None
    created_at: datetime | None = None


@dataclass
class Confirmation:
    id: UUID
    proposal_id: UUID
    status: ConfirmationStatus
    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None
    created_task_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    expires_at: datetime | None = None


@dataclass
class Task:
    id: UUID
    public_id: str
    title: str
    status: TaskStatus
    priority: TaskPriority
    source: TaskSource
    project_id: UUID | None = None
    description: str | None = None
    assignee_id: UUID | None = None
    assignee_text: str | None = None
    deadline: datetime | None = None
    source_message_id: UUID | None = None
    created_from_proposal_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    last_status_update_at: datetime | None = None


@dataclass
class BoardCard:
    id: UUID
    task_id: UUID
    provider: BoardProvider
    external_card_id: str
    external_url: str | None = None
    external_payload: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ReminderLog:
    id: UUID
    task_id: UUID
    kind: ReminderKind
    recipient_telegram_user_id: int | None = None
    telegram_chat_id: int | None = None
    sent_at: datetime | None = None
    payload: dict[str, Any] | None = None


@dataclass
class DigestLog:
    id: UUID
    telegram_user_id: int | None = None
    telegram_chat_id: int | None = None
    sent_at: datetime | None = None
    payload: dict[str, Any] | None = None


@dataclass
class AuditLog:
    id: UUID
    actor_type: str
    action: str
    entity_type: str
    actor_id: str | None = None
    entity_id: UUID | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime | None = None


@dataclass
class UserXpEvent:
    id: UUID
    user_id: UUID
    kind: XpEventKind
    points: int
    reason: str
    workspace_id: UUID | None = None
    task_id: UUID | None = None
    meeting_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class UserXpTotal:
    id: UUID
    user_id: UUID
    points_total: int
    level: int
    workspace_id: UUID | None = None
    updated_at: datetime | None = None
