"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-02

Создаёт полную схему P0 Grey Cardinal.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("telegram_username", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "projects",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("default_chat_id", UUID, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "telegram_chats",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", UUID, sa.ForeignKey("telegram_chats.id"), nullable=False),
        sa.Column("sender_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("raw_json", JSONB, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("chat_id", "telegram_message_id", name="uq_chat_message"),
    )

    op.create_table(
        "task_proposals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "source_message_id", UUID, sa.ForeignKey("chat_messages.id"), nullable=True
        ),
        sa.Column("source_transcript_id", UUID, nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assignee_text", sa.Text(), nullable=True),
        sa.Column("assignee_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deadline", TS, nullable=True),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("extractor_payload", JSONB, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "confirmations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("proposal_id", UUID, sa.ForeignKey("task_proposals.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_task_id", UUID, nullable=True),
        sa.Column("expires_at", TS, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False, unique=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column("assignee_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assignee_text", sa.Text(), nullable=True),
        sa.Column("deadline", TS, nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "source_message_id", UUID, sa.ForeignKey("chat_messages.id"), nullable=True
        ),
        sa.Column(
            "created_from_proposal_id",
            UUID,
            sa.ForeignKey("task_proposals.id"),
            nullable=True,
        ),
        sa.Column("completed_at", TS, nullable=True),
        sa.Column("last_status_update_at", TS, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "board_cards",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), nullable=False, unique=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_card_id", sa.Text(), nullable=False),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("external_payload", JSONB, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "transcript_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("meeting_id", sa.Text(), nullable=True),
        sa.Column("speaker_id", sa.Text(), nullable=True),
        sa.Column("speaker_name", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("ts", TS, nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("raw_json", JSONB, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "reminder_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("recipient_telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("sent_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
    )

    op.create_table(
        "digest_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("sent_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", UUID, nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_deadline", "tasks", ["deadline"])
    op.create_index("ix_reminder_logs_task_kind", "reminder_logs", ["task_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_reminder_logs_task_kind", table_name="reminder_logs")
    op.drop_index("ix_tasks_deadline", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    for table in (
        "audit_logs",
        "digest_logs",
        "reminder_logs",
        "transcript_events",
        "board_cards",
        "tasks",
        "confirmations",
        "task_proposals",
        "chat_messages",
        "telegram_chats",
        "projects",
        "users",
    ):
        op.drop_table(table)
