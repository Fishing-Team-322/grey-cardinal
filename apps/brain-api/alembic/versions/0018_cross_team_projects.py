"""cross-team projects, shared tasks, project contexts

Revision ID: 0018_cross_team_projects
Revises: 0017_team_pet_full
Create Date: 2026-06-11
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "0018_cross_team_projects"
down_revision = "0017_team_pet_full"
branch_labels = None
depends_on = None

UUID = sa.Uuid()


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    tables = _tables()

    if "company_projects" not in tables:
        op.create_table(
            "company_projects",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("company_id", UUID, sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("code", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("expected_result", sa.Text(), nullable=True),
            sa.Column("status", sa.Text(), nullable=False, server_default="active"),
            sa.Column("owner_id", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("budget_min", sa.Integer(), nullable=True),
            sa.Column("budget_max", sa.Integer(), nullable=True),
            sa.Column("source", sa.Text(), nullable=False, server_default="manual"),
            sa.Column("sync_status", sa.Text(), nullable=False, server_default="local_only"),
            sa.Column("sync_error", sa.Text(), nullable=True),
            sa.Column("settings", sa.JSON(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.UniqueConstraint("company_id", "code", name="uq_company_project_code"),
            sa.CheckConstraint(
                "status in ('draft','active','paused','completed','cancelled')",
                name="ck_company_project_status",
            ),
        )
        op.create_index(
            "ix_company_project_company_status", "company_projects", ["company_id", "status"]
        )

    if "company_project_drafts" not in tables:
        op.create_table(
            "company_project_drafts",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("company_id", UUID, sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("source_team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("generated_name", sa.Text(), nullable=False),
            sa.Column("horizon_weeks", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
        )
        op.create_index(
            "ix_project_draft_company_created",
            "company_project_drafts",
            ["company_id", "created_at"],
        )

    if "project_teams" not in tables:
        op.create_table(
            "project_teams",
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "project_id",
                UUID,
                sa.ForeignKey("company_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("role", sa.Text(), nullable=False, server_default="contributor"),
            sa.Column("allocation_percent", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("participation_status", sa.Text(), nullable=False, server_default="active"),
            sa.Column(
                "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.UniqueConstraint("project_id", "team_id", name="uq_project_team"),
            sa.CheckConstraint(
                "role in ('lead','contributor','observer')", name="ck_project_team_role"
            ),
            sa.CheckConstraint(
                "participation_status in ('active','pending','declined')",
                name="ck_project_team_participation",
            ),
        )
        op.create_index("ix_project_team_team", "project_teams", ["team_id", "project_id"])

    if "project_members" not in tables:
        op.create_table(
            "project_members",
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "project_id",
                UUID,
                sa.ForeignKey("company_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
            sa.Column("role", sa.Text(), nullable=False, server_default="contributor"),
            sa.Column("allocation_percent", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column(
                "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
            sa.CheckConstraint(
                "role in ('owner','manager','contributor','observer')",
                name="ck_project_member_role",
            ),
        )
        op.create_index("ix_project_member_user", "project_members", ["user_id", "project_id"])

    if "tasks" in tables and "company_project_id" not in _columns("tasks"):
        op.add_column(
            "tasks",
            sa.Column(
                "company_project_id", UUID, sa.ForeignKey("company_projects.id"), nullable=True
            ),
        )
        op.create_index("ix_task_company_project", "tasks", ["company_project_id", "status"])

    if "task_teams" not in tables:
        op.create_table(
            "task_teams",
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "task_id", UUID, sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("role", sa.Text(), nullable=False, server_default="contributor"),
            sa.UniqueConstraint("task_id", "team_id", name="uq_task_team_participant"),
            sa.CheckConstraint(
                "role in ('owner','contributor','reviewer')", name="ck_task_team_role"
            ),
        )
        op.create_index("ix_task_team_team", "task_teams", ["team_id", "task_id"])

    if "task_assignees" not in tables:
        op.create_table(
            "task_assignees",
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "task_id", UUID, sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.Text(), nullable=False, server_default="contributor"),
            sa.UniqueConstraint("task_id", "user_id", name="uq_task_assignee"),
            sa.CheckConstraint(
                "role in ('owner','contributor','reviewer')", name="ck_task_assignee_role"
            ),
        )
        op.create_index("ix_task_assignee_user", "task_assignees", ["user_id", "task_id"])

    if "project_external_links" not in tables:
        op.create_table(
            "project_external_links",
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "project_id",
                UUID,
                sa.ForeignKey("company_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("provider", sa.Text(), nullable=False),
            sa.Column("source_team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("external_project_id", sa.Text(), nullable=True),
            sa.Column("external_board_id", sa.Text(), nullable=True),
            sa.Column("external_url", sa.Text(), nullable=True),
            sa.Column("sync_status", sa.Text(), nullable=False, server_default="pending"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.UniqueConstraint("project_id", "provider", name="uq_project_external_provider"),
        )

    if "project_chat_bindings" not in tables:
        op.create_table(
            "project_chat_bindings",
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "project_id",
                UUID,
                sa.ForeignKey("company_projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "telegram_chat_id",
                UUID,
                sa.ForeignKey("telegram_chats.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("message_thread_id", sa.BigInteger(), nullable=True),
            sa.Column("kind", sa.Text(), nullable=False, server_default="project"),
            sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.UniqueConstraint(
                "telegram_chat_id",
                "message_thread_id",
                name="uq_project_chat_binding",
            ),
        )
        op.create_index(
            "ix_project_chat_context",
            "project_chat_bindings",
            ["telegram_chat_id", "message_thread_id"],
        )
        op.create_index(
            "uq_project_chat_default",
            "project_chat_bindings",
            ["telegram_chat_id"],
            unique=True,
            postgresql_where=sa.text("message_thread_id IS NULL"),
            sqlite_where=sa.text("message_thread_id IS NULL"),
        )

    if "collaboration_events" not in tables:
        op.create_table(
            "collaboration_events",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("company_id", UUID, sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("project_id", UUID, sa.ForeignKey("company_projects.id"), nullable=True),
            sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), nullable=True),
            sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("source_team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
            sa.Column("target_team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("idempotency_key", sa.Text(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.UniqueConstraint("idempotency_key", name="uq_collaboration_event_key"),
        )
        op.create_index(
            "ix_collaboration_company_created",
            "collaboration_events",
            ["company_id", "created_at"],
        )


def downgrade() -> None:
    tables = _tables()
    for table in (
        "collaboration_events",
        "project_chat_bindings",
        "project_external_links",
        "task_assignees",
        "task_teams",
    ):
        if table in tables:
            op.drop_table(table)
    if "tasks" in tables and "company_project_id" in _columns("tasks"):
        with contextlib.suppress(Exception):
            op.drop_index("ix_task_company_project", table_name="tasks")
        with op.batch_alter_table("tasks") as batch:
            batch.drop_column("company_project_id")
    for table in (
        "project_members",
        "project_teams",
        "company_project_drafts",
        "company_projects",
    ):
        if table in tables:
            op.drop_table(table)
