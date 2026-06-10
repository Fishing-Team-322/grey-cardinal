"""pending chat actions (task reassignment / cancellation from chat)

Revision ID: 0015_pending_chat_actions
Revises: 0014_meeting_agent_recorder
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_pending_chat_actions"
down_revision = "0014_meeting_agent_recorder"
branch_labels = None
depends_on = None

UUID = sa.Uuid()


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "pending_chat_actions" in _tables():
        return
    op.create_table(
        "pending_chat_actions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("target_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("requested_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("source_message_id", UUID, sa.ForeignKey("chat_messages.id"), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("decided_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_pending_chat_action_status",
        "pending_chat_actions",
        ["team_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pending_chat_action_status", table_name="pending_chat_actions")
    op.drop_table("pending_chat_actions")
