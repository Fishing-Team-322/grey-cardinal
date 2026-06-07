"""Add Telegram account linking codes.

Revision ID: 0007_telegram_link_codes
Revises: 0006_chat_confirmation_mode
Create Date: 2026-06-05
"""
# ruff: noqa: E501
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0007_telegram_link_codes"
down_revision = "0006_chat_confirmation_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_link_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_telegram_link_codes_code", "telegram_link_codes", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_telegram_link_codes_code", table_name="telegram_link_codes")
    op.drop_table("telegram_link_codes")
