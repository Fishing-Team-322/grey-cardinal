"""P1 meeting lifecycle and transcript metadata.

Revision ID: 0002_p1_meetings
Revises: 0001_initial
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_p1_meetings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False, unique=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("telegram_chat_id", UUID, sa.ForeignKey("telegram_chats.id"), nullable=True),
        sa.Column("external_source", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("stopped_at", TS, nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.add_column("transcript_events", sa.Column("meeting_db_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_transcript_events_meeting_db_id",
        "transcript_events",
        "meetings",
        ["meeting_db_id"],
        ["id"],
    )
    op.add_column("transcript_events", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column(
        "transcript_events",
        sa.Column("source", sa.Text(), nullable=False, server_default="audio_worker"),
    )
    op.create_index("ix_meetings_status", "meetings", ["status"])


def downgrade() -> None:
    op.drop_index("ix_meetings_status", table_name="meetings")
    op.drop_column("transcript_events", "source")
    op.drop_column("transcript_events", "confidence")
    op.drop_constraint(
        "fk_transcript_events_meeting_db_id", "transcript_events", type_="foreignkey"
    )
    op.drop_column("transcript_events", "meeting_db_id")
    op.drop_table("meetings")
