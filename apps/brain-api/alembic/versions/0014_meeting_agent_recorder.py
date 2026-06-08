"""meeting agent recorder lifecycle

Revision ID: 0014_meeting_agent_recorder
Revises: 0013_share_links
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_meeting_agent_recorder"
down_revision = "0013_share_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_meeting_agent_join_status",
        "meeting_agent_join_jobs",
        type_="check",
    )
    op.add_column("meeting_agent_join_jobs", sa.Column("worker_id", sa.Text(), nullable=True))
    op.add_column(
        "meeting_agent_join_jobs",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "meeting_agent_join_jobs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "meeting_agent_join_jobs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "meeting_agent_join_jobs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_meeting_agent_join_status",
        "meeting_agent_join_jobs",
        "status in ('pending','queued','joining','recording','stop_requested','failed','completed')",
    )
    op.create_index(
        "ix_meeting_agent_join_jobs_status_created",
        "meeting_agent_join_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_meeting_agent_join_jobs_status_created", table_name="meeting_agent_join_jobs")
    op.drop_constraint(
        "ck_meeting_agent_join_status",
        "meeting_agent_join_jobs",
        type_="check",
    )
    op.drop_column("meeting_agent_join_jobs", "completed_at")
    op.drop_column("meeting_agent_join_jobs", "heartbeat_at")
    op.drop_column("meeting_agent_join_jobs", "started_at")
    op.drop_column("meeting_agent_join_jobs", "attempts")
    op.drop_column("meeting_agent_join_jobs", "worker_id")
    op.create_check_constraint(
        "ck_meeting_agent_join_status",
        "meeting_agent_join_jobs",
        "status in ('pending','queued','failed','completed')",
    )
