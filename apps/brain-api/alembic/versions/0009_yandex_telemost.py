"""yandex telemost: oauth integration, oauth states, meeting agent join jobs

Revision ID: 0009_yandex_telemost
Revises: 0008_relax_legacy_ai_inbox
Create Date: 2026-06-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009_yandex_telemost"
down_revision = "0008_relax_legacy_ai_inbox"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "yandex_telemost_integrations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False, server_default="yandex_telemost"),
        sa.Column("yandex_user_id", sa.Text(), nullable=True),
        sa.Column("access_token_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="disconnected"),
        sa.Column("settings", JSON_TYPE, nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("team_id", name="uq_yandex_telemost_team"),
        sa.CheckConstraint(
            "status in ('connected','expired','disconnected','error')",
            name="ck_yandex_telemost_status",
        ),
    )

    op.create_table(
        "yandex_oauth_states",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False, server_default="yandex_telemost"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("state", name="uq_yandex_oauth_state"),
    )
    op.create_index("ix_yandex_oauth_states_state", "yandex_oauth_states", ["state"])

    op.create_table(
        "meeting_agent_join_jobs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False, server_default="yandex_telemost"),
        sa.Column("meeting_url", sa.Text(), nullable=False),
        sa.Column("conference_id", sa.Text(), nullable=True),
        sa.Column("meeting_id", UUID, sa.ForeignKey("meetings.id"), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('pending','queued','failed','completed')",
            name="ck_meeting_agent_join_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("meeting_agent_join_jobs")
    op.drop_index("ix_yandex_oauth_states_state", table_name="yandex_oauth_states")
    op.drop_table("yandex_oauth_states")
    op.drop_table("yandex_telemost_integrations")
