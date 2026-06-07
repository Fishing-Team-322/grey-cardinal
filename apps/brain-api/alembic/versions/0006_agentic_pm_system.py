"""agentic PM system, full YouGile sync, Grey Board

Revision ID: 0006_agentic_pm_system
Revises: 0005_team_board_provider_mock
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_agentic_pm_system"
down_revision = "0005_team_board_provider_mock"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("message_thread_id", sa.BigInteger(), nullable=True))
    op.add_column("tasks", sa.Column("source_type", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("source_id", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("source_text", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("source_payload", JSONB, nullable=True))
    op.add_column("absence_periods", sa.Column("delegate_to_user_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_absence_delegate_user",
        "absence_periods",
        "users",
        ["delegate_to_user_id"],
        ["id"],
    )

    op.create_table(
        "yougile_connections",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("provider", sa.Text(), server_default="yougile", nullable=False),
        sa.Column("credentials_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "yougile_workspaces",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("connection_id", UUID, sa.ForeignKey("yougile_connections.id"), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "external_id", name="uq_yougile_workspace_external"),
    )
    op.create_table(
        "yougile_projects",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("connection_id", UUID, sa.ForeignKey("yougile_connections.id"), nullable=False),
        sa.Column("workspace_id", UUID, sa.ForeignKey("yougile_workspaces.id"), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "external_id", name="uq_yougile_project_external"),
    )
    op.create_table(
        "yougile_boards",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("connection_id", UUID, sa.ForeignKey("yougile_connections.id"), nullable=False),
        sa.Column("project_id", UUID, sa.ForeignKey("yougile_projects.id"), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_selected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "external_id", name="uq_yougile_board_external"),
    )
    op.create_table(
        "yougile_columns",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("board_id", UUID, sa.ForeignKey("yougile_boards.id"), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("mapped_status", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("board_id", "external_id", name="uq_yougile_column_external"),
    )
    op.create_table(
        "external_task_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_board_id", sa.Text(), nullable=True),
        sa.Column("external_column_id", sa.Text(), nullable=True),
        sa.Column("external_task_id", sa.Text(), nullable=False),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.UniqueConstraint("provider", "external_task_id", name="uq_external_task_provider_id"),
    )
    op.create_table(
        "sync_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", UUID, nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sync_events_team_created", "sync_events", ["team_id", "created_at"])
    op.create_table(
        "ai_inbox_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("parsed_payload", JSONB, nullable=True),
        sa.Column("proposed_action", sa.Text(), nullable=True),
        sa.Column("linked_task_id", UUID, sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("decided_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "agent_recommendations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "telegram_topic_bindings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("telegram_chat_id", UUID, sa.ForeignKey("telegram_chats.id"), nullable=False),
        sa.Column("message_thread_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("board_id", UUID, sa.ForeignKey("yougile_boards.id"), nullable=True),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("telegram_chat_id", "message_thread_id", name="uq_telegram_topic_binding"),
    )


def downgrade() -> None:
    op.drop_table("telegram_topic_bindings")
    op.drop_table("agent_recommendations")
    op.drop_table("ai_inbox_items")
    op.drop_index("ix_sync_events_team_created", table_name="sync_events")
    op.drop_table("sync_events")
    op.drop_table("external_task_links")
    op.drop_table("yougile_columns")
    op.drop_table("yougile_boards")
    op.drop_table("yougile_projects")
    op.drop_table("yougile_workspaces")
    op.drop_table("yougile_connections")
    op.drop_constraint("fk_absence_delegate_user", "absence_periods", type_="foreignkey")
    op.drop_column("absence_periods", "delegate_to_user_id")
    op.drop_column("tasks", "source_payload")
    op.drop_column("tasks", "source_url")
    op.drop_column("tasks", "source_text")
    op.drop_column("tasks", "source_id")
    op.drop_column("tasks", "source_type")
    op.drop_column("chat_messages", "message_thread_id")
