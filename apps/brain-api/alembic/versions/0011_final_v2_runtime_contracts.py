"""final v2 runtime contracts

Revision ID: 0011_final_v2_runtime_contracts
Revises: 0010_reconcile_agentic_models
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_final_v2_runtime_contracts"
down_revision = "0010_reconcile_agentic_models"
branch_labels = None
depends_on = None

UUID = sa.Uuid()


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    names = {item["name"] for item in inspector.get_unique_constraints(table)}
    names.update({item["name"] for item in inspector.get_indexes(table) if item.get("unique")})
    return {name for name in names if name}


def upgrade() -> None:
    tables = _tables()
    if "telegram_team_bind_codes" not in tables:
        op.create_table(
            "telegram_team_bind_codes",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("code", sa.Text(), nullable=False),
            sa.Column("created_by", UUID, sa.ForeignKey("users.id")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("code", name="uq_telegram_team_bind_code"),
        )
        op.create_index(
            "ix_telegram_team_bind_codes_code",
            "telegram_team_bind_codes",
            ["code"],
        )

    constraints = _constraints("tasks")
    for name in ("tasks_public_id_key", "ix_tasks_public_id", "uq_tasks_public_id"):
        if name in constraints:
            op.drop_constraint(name, "tasks", type_="unique")
    for name in ("tasks_seq_key", "ix_tasks_seq", "uq_tasks_seq"):
        if name in constraints:
            op.drop_constraint(name, "tasks", type_="unique")
    constraints = _constraints("tasks")
    if "uq_task_team_public_id" not in constraints:
        op.create_unique_constraint("uq_task_team_public_id", "tasks", ["team_id", "public_id"])
    if "uq_task_team_seq" not in constraints:
        op.create_unique_constraint("uq_task_team_seq", "tasks", ["team_id", "seq"])

    meeting_columns = {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns("meetings")}
    if "started_at" in meeting_columns and not meeting_columns["started_at"].get("nullable", True):
        op.alter_column(
            "meetings",
            "started_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )


def downgrade() -> None:
    pass
