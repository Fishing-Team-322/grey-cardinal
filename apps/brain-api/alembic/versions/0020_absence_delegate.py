"""add absence delegation metadata

Revision ID: 0020_absence_delegate
Revises: 0019_task_source_metadata
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_absence_delegate"
down_revision = "0019_task_source_metadata"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
FK_NAME = "fk_absence_periods_delegate_to_user"


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _foreign_key_columns(table: str) -> set[tuple[str, ...]]:
    return {
        tuple(foreign_key["constrained_columns"])
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table)
    }


def upgrade() -> None:
    if "delegate_to_user_id" not in _columns("absence_periods"):
        op.add_column(
            "absence_periods",
            sa.Column("delegate_to_user_id", UUID, nullable=True),
        )
    if ("delegate_to_user_id",) not in _foreign_key_columns("absence_periods"):
        op.create_foreign_key(
            FK_NAME,
            "absence_periods",
            "users",
            ["delegate_to_user_id"],
            ["id"],
        )


def downgrade() -> None:
    if ("delegate_to_user_id",) in _foreign_key_columns("absence_periods"):
        op.drop_constraint(FK_NAME, "absence_periods", type_="foreignkey")
    if "delegate_to_user_id" in _columns("absence_periods"):
        op.drop_column("absence_periods", "delegate_to_user_id")
