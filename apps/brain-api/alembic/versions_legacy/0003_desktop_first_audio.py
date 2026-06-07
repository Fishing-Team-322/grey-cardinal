"""Desktop-first audio identity and gamification.

Revision ID: 0003_desktop_first_audio
Revises: 0002_p1_meetings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_desktop_first_audio"
down_revision = "0002_p1_meetings"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", UUID, nullable=True),
        sa.Column("device_name", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("app_version", sa.Text(), nullable=True),
        sa.Column("device_fingerprint", sa.Text(), nullable=True),
        sa.Column("last_seen_at", TS, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "client_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", UUID, sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("workspace_id", UUID, nullable=True),
        sa.Column("session_token_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("last_seen_at", TS, nullable=True),
        sa.Column("expires_at", TS, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "meeting_participants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("meeting_id", UUID, sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", UUID, sa.ForeignKey("devices.id"), nullable=True),
        sa.Column(
            "client_session_id", UUID, sa.ForeignKey("client_sessions.id"), nullable=True
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("joined_at", TS, nullable=False),
        sa.Column("left_at", TS, nullable=True),
        sa.Column("last_seen_at", TS, nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("meeting_id", "user_id", name="uq_meeting_participant_user"),
    )
    op.create_table(
        "user_xp_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", UUID, nullable=True),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("meeting_id", UUID, sa.ForeignKey("meetings.id"), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "user_xp_totals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", UUID, nullable=True),
        sa.Column("points_total", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "workspace_id", name="uq_user_xp_total_scope"),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])
    op.create_index("ix_client_sessions_user_device", "client_sessions", ["user_id", "device_id"])
    op.create_index("ix_user_xp_events_user_kind", "user_xp_events", ["user_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_user_xp_events_user_kind", table_name="user_xp_events")
    op.drop_index("ix_client_sessions_user_device", table_name="client_sessions")
    op.drop_index("ix_devices_user_id", table_name="devices")
    op.drop_table("user_xp_totals")
    op.drop_table("user_xp_events")
    op.drop_table("meeting_participants")
    op.drop_table("client_sessions")
    op.drop_table("devices")
