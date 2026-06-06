"""device_link_codes: one-time agent pairing codes (replaces demo AgentsStore)

Revision ID: 0003_device_link_codes
Revises: 0002_drop_legacy_organizations
Create Date: 2026-06-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_device_link_codes"
down_revision = "0002_drop_legacy_organizations"
branch_labels = None
depends_on = None

UUID = sa.Uuid()


def upgrade() -> None:
    op.create_table(
        "device_link_codes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("code", name="uq_device_link_code"),
    )
    op.create_index("ix_device_link_codes_code", "device_link_codes", ["code"])


def downgrade() -> None:
    op.drop_index("ix_device_link_codes_code", table_name="device_link_codes")
    op.drop_table("device_link_codes")
