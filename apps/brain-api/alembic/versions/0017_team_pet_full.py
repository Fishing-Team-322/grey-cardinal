"""team pet full feature: scores, events, inventory, privacy, battles

Revision ID: 0017_team_pet_full
Revises: 0016_emotion_and_pet
Create Date: 2026-06-11
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "0017_team_pet_full"
down_revision = "0016_emotion_and_pet"
branch_labels = None
depends_on = None

UUID = sa.Uuid()


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    tables = _tables()

    # --- 1. extend team_pets with scores / appearance ---
    if "team_pets" in tables:
        existing = _columns("team_pets")
        score_cols = (
            "power_score",
            "productivity_score",
            "harmony_score",
            "communication_score",
            "wellbeing_score",
            "stability_score",
            "tension_score",
        )
        for col in score_cols:
            if col not in existing:
                op.add_column(
                    "team_pets",
                    sa.Column(col, sa.Float(), nullable=False, server_default="0"),
                )
        for col in ("current_skin", "current_background", "current_aura", "current_emotion"):
            if col not in existing:
                op.add_column("team_pets", sa.Column(col, sa.Text(), nullable=True))
        if "current_accessories" not in existing:
            op.add_column("team_pets", sa.Column("current_accessories", sa.JSON(), nullable=True))
        if "last_scored_at" not in existing:
            op.add_column(
                "team_pets",
                sa.Column("last_scored_at", sa.DateTime(timezone=True), nullable=True),
            )

    # --- 2. team_pet_events ---
    if "team_pet_events" not in tables:
        op.create_table(
            "team_pet_events",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("pet_id", UUID, sa.ForeignKey("team_pets.id"), nullable=False),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("source_type", sa.Text(), nullable=True),
            sa.Column("source_id", UUID, nullable=True),
            sa.Column("points_delta", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metric", sa.Text(), nullable=False, server_default="xp"),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_team_pet_event_team_ts", "team_pet_events", ["team_id", "created_at"]
        )
        op.create_index(
            "ix_team_pet_event_pet_ts", "team_pet_events", ["pet_id", "created_at"]
        )
        op.create_index(
            "ix_team_pet_event_type_ts", "team_pet_events", ["event_type", "created_at"]
        )

    # --- 3. team_pet_inventory ---
    if "team_pet_inventory" not in tables:
        op.create_table(
            "team_pet_inventory",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("item_id", sa.Text(), nullable=False),
            sa.Column("item_type", sa.Text(), nullable=False),
            sa.Column("rarity", sa.Text(), nullable=False, server_default="common"),
            sa.Column("status", sa.Text(), nullable=False, server_default="locked"),
            sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("equipped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("unlock_reason", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
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
            sa.UniqueConstraint("team_id", "item_id", name="uq_team_pet_inventory_item"),
        )
        op.create_index(
            "ix_team_pet_inventory_team", "team_pet_inventory", ["team_id", "item_type"]
        )

    # --- 4. team_pet_privacy_settings ---
    if "team_pet_privacy_settings" not in tables:
        op.create_table(
            "team_pet_privacy_settings",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("analyze_tasks", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("analyze_chat", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("analyze_calls", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("analyze_camera", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("team_aggregates_only", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column(
                "manager_individual_signals", sa.Boolean(), nullable=False, server_default="0"
            ),
            sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("visible_to", sa.Text(), nullable=False, server_default="managers"),
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
            sa.UniqueConstraint("team_id", name="uq_team_pet_privacy_team"),
        )

    # --- 5. team_battles ---
    if "team_battles" not in tables:
        op.create_table(
            "team_battles",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("period", sa.Text(), nullable=False),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="active"),
            sa.Column("reward_item_id", sa.Text(), nullable=True),
            sa.Column("winner_team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
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
            sa.UniqueConstraint("period", name="uq_team_battle_period"),
        )

    # --- 6. team_battle_scores ---
    if "team_battle_scores" not in tables:
        op.create_table(
            "team_battle_scores",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("battle_id", UUID, sa.ForeignKey("team_battles.id"), nullable=False),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("pet_id", UUID, sa.ForeignKey("team_pets.id"), nullable=True),
            sa.Column("power_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rank", sa.Integer(), nullable=True),
            sa.Column("streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rewards", sa.JSON(), nullable=True),
            sa.Column("snapshot", sa.JSON(), nullable=True),
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
            sa.UniqueConstraint("battle_id", "team_id", name="uq_team_battle_score_team"),
        )
        op.create_index(
            "ix_team_battle_score_power", "team_battle_scores", ["battle_id", "power_score"]
        )
        op.create_index(
            "ix_team_battle_score_team", "team_battle_scores", ["team_id", "battle_id"]
        )


def downgrade() -> None:
    tables = _tables()
    if "team_battle_scores" in tables:
        op.drop_table("team_battle_scores")
    if "team_battles" in tables:
        op.drop_table("team_battles")
    if "team_pet_privacy_settings" in tables:
        op.drop_table("team_pet_privacy_settings")
    if "team_pet_inventory" in tables:
        op.drop_table("team_pet_inventory")
    if "team_pet_events" in tables:
        op.drop_table("team_pet_events")
    if "team_pets" in tables:
        for col in (
            "last_scored_at",
            "current_accessories",
            "current_emotion",
            "current_aura",
            "current_background",
            "current_skin",
            "tension_score",
            "stability_score",
            "wellbeing_score",
            "communication_score",
            "harmony_score",
            "productivity_score",
            "power_score",
        ):
            with op.batch_alter_table("team_pets") as batch, contextlib.suppress(Exception):
                batch.drop_column(col)
