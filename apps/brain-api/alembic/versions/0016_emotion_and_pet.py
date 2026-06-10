"""emotional portrait signals + team tamagotchi pet

Revision ID: 0016_emotion_and_pet
Revises: 0015_pending_chat_actions
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_emotion_and_pet"
down_revision = "0015_pending_chat_actions"
branch_labels = None
depends_on = None

UUID = sa.Uuid()


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "emotion_signals" not in tables:
        op.create_table(
            "emotion_signals",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Column("valence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("arousal", sa.Float(), nullable=False, server_default="0"),
            sa.Column("stress", sa.Float(), nullable=False, server_default="0"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("source_ref", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_emotion_signal_team_ts", "emotion_signals", ["team_id", "created_at"]
        )
        op.create_index(
            "ix_emotion_signal_user_ts", "emotion_signals", ["user_id", "created_at"]
        )

    if "team_pets" not in tables:
        op.create_table(
            "team_pets",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False, unique=True),
            sa.Column("name", sa.Text(), nullable=False, server_default="Кардиналыч"),
            sa.Column("species", sa.Text(), nullable=False, server_default="fox"),
            sa.Column("mood", sa.Float(), nullable=False, server_default="0.6"),
            sa.Column("energy", sa.Float(), nullable=False, server_default="0.7"),
            sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_fed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_decay_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_table("team_pets")
    op.drop_index("ix_emotion_signal_user_ts", table_name="emotion_signals")
    op.drop_index("ix_emotion_signal_team_ts", table_name="emotion_signals")
    op.drop_table("emotion_signals")
