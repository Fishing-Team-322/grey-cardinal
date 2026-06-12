"""add task source metadata columns

Revision ID: 0019_task_source_metadata
Revises: 0018_cross_team_projects
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019_task_source_metadata"
down_revision = "0018_cross_team_projects"
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    columns = _columns("tasks")
    for name, column in (
        ("source_type", sa.Column("source_type", sa.Text(), nullable=True)),
        ("source_id", sa.Column("source_id", sa.Text(), nullable=True)),
        ("source_text", sa.Column("source_text", sa.Text(), nullable=True)),
        ("source_url", sa.Column("source_url", sa.Text(), nullable=True)),
        ("source_payload", sa.Column("source_payload", JSON_TYPE, nullable=True)),
    ):
        if name not in columns:
            op.add_column("tasks", column)


def downgrade() -> None:
    columns = _columns("tasks")
    for name in ("source_payload", "source_url", "source_text", "source_id", "source_type"):
        if name in columns:
            op.drop_column("tasks", name)
