"""yougile_mappings + yougile_sync_log

board_config (already JSONB on teams) gains schemaless YouGile keys
(yougile_company_id, yougile_project_id, default_column_ids, webhook_secret, ...)
— no migration needed for those.

Revision ID: 0004_yougile_integration
Revises: 0003_device_link_codes
Create Date: 2026-06-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_yougile_integration"
down_revision = "0003_device_link_codes"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "yougile_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("local_id", UUID, nullable=True),
        sa.Column("yougile_id", sa.Text(), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type in ('project','board','column','task','user')",
            name="ck_yougile_mapping_entity",
        ),
        sa.UniqueConstraint("team_id", "entity_type", "yougile_id", name="uq_yougile_mapping"),
    )
    op.create_index(
        "ix_yougile_mapping_local", "yougile_mappings", ["team_id", "entity_type", "local_id"]
    )
    op.create_table(
        "yougile_sync_log",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("yougile_id", sa.Text(), nullable=True),
        sa.Column("local_id", UUID, nullable=True),
        sa.Column("event", sa.Text(), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "direction in ('inbound','outbound')", name="ck_yougile_synclog_direction"
        ),
    )
    op.create_index(
        "ix_yougile_synclog_team_created", "yougile_sync_log", ["team_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_yougile_synclog_team_created", table_name="yougile_sync_log")
    op.drop_table("yougile_sync_log")
    op.drop_index("ix_yougile_mapping_local", table_name="yougile_mappings")
    op.drop_table("yougile_mappings")
