"""share links (public summary/digest pages)

Revision ID: 0013_share_links
Revises: 0012_task_comments
Create Date: 2026-06-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_share_links"
down_revision = "0012_task_comments"
branch_labels = None
depends_on = None

UUID = sa.Uuid()


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "share_links" in _tables():
        return
    op.create_table(
        "share_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=True),
        sa.Column("ref_id", UUID, nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_share_links_token", "share_links", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_share_links_token", table_name="share_links")
    op.drop_table("share_links")
