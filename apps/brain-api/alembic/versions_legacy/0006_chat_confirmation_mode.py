"""Add per-chat task confirmation mode.

Revision ID: 0006_chat_confirmation_mode
Revises: 0005_organizations
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_chat_confirmation_mode"
down_revision = "0005_organizations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "telegram_chats",
        sa.Column(
            "task_confirmation_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("telegram_chats", "task_confirmation_required")
