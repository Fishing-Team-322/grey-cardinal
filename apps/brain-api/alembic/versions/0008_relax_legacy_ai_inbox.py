"""relax legacy AI inbox columns

Revision ID: 0008_relax_legacy_ai_inbox
Revises: 0007_agentic_board_mirror
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_relax_legacy_ai_inbox"
down_revision = "0007_agentic_board_mirror"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"] for column in inspector.get_columns("ai_inbox_items")
    }
    if "source_type" in columns:
        op.alter_column(
            "ai_inbox_items",
            "source_type",
            existing_type=sa.Text(),
            nullable=True,
        )


def downgrade() -> None:
    pass
