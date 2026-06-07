"""reconcile legacy and v2 agentic model columns

Revision ID: 0010_reconcile_agentic_models
Revises: 0009_yandex_telemost
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_reconcile_agentic_models"
down_revision = "0009_yandex_telemost"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    inbox_columns = _columns("ai_inbox_items")
    for name, column in (
        ("item_type", sa.Column("item_type", sa.Text())),
        ("source_type", sa.Column("source_type", sa.Text())),
        ("source_id", sa.Column("source_id", sa.Text())),
        ("source_text", sa.Column("source_text", sa.Text())),
        ("parsed_payload", sa.Column("parsed_payload", JSONB)),
        ("proposed_action", sa.Column("proposed_action", sa.Text())),
        ("linked_task_id", sa.Column("linked_task_id", UUID, sa.ForeignKey("tasks.id"))),
        ("decided_by", sa.Column("decided_by", UUID, sa.ForeignKey("users.id"))),
        ("decided_at", sa.Column("decided_at", sa.DateTime(timezone=True))),
    ):
        if name not in inbox_columns:
            op.add_column("ai_inbox_items", column)

    for name in ("kind", "reason", "raw_text"):
        if name in inbox_columns:
            op.alter_column(
                "ai_inbox_items",
                name,
                existing_type=sa.Text(),
                nullable=True,
            )
    op.alter_column(
        "ai_inbox_items",
        "confidence",
        existing_type=sa.Float(),
        server_default="0",
        nullable=False,
    )

    connection_columns = _columns("yougile_connections")
    for name, column in (
        (
            "provider",
            sa.Column("provider", sa.Text(), server_default="yougile", nullable=False),
        ),
        ("credentials_encrypted", sa.Column("credentials_encrypted", sa.LargeBinary())),
        ("last_error", sa.Column("last_error", sa.Text())),
    ):
        if name not in connection_columns:
            op.add_column("yougile_connections", column)
    if "external_company_id" in connection_columns:
        op.alter_column(
            "yougile_connections",
            "external_company_id",
            existing_type=sa.Text(),
            nullable=True,
        )

    if "yougile_workspaces" not in tables:
        op.create_table(
            "yougile_workspaces",
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "connection_id",
                UUID,
                sa.ForeignKey("yougile_connections.id"),
                nullable=False,
            ),
            sa.Column("external_id", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("raw_payload", JSONB),
            sa.Column("synced_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint(
                "connection_id",
                "external_id",
                name="uq_yougile_workspace_external",
            ),
        )

    if "yougile_projects" not in tables:
        op.create_table(
            "yougile_projects",
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "connection_id",
                UUID,
                sa.ForeignKey("yougile_connections.id"),
                nullable=False,
            ),
            sa.Column("workspace_id", UUID, sa.ForeignKey("yougile_workspaces.id")),
            sa.Column("external_id", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("raw_payload", JSONB),
            sa.Column("synced_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint(
                "connection_id",
                "external_id",
                name="uq_yougile_project_external",
            ),
        )

    board_columns = _columns("yougile_boards")
    if "project_id" not in board_columns:
        op.add_column(
            "yougile_boards",
            sa.Column("project_id", UUID, sa.ForeignKey("yougile_projects.id")),
        )

    if "agent_recommendations" not in tables:
        op.create_table(
            "agent_recommendations",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("company_id", UUID, sa.ForeignKey("companies.id")),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id")),
            sa.Column("task_id", UUID, sa.ForeignKey("tasks.id")),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id")),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("severity", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), server_default="open", nullable=False),
            sa.Column("action", sa.Text()),
            sa.Column("payload", JSONB),
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

    if "telegram_topic_bindings" not in tables:
        op.create_table(
            "telegram_topic_bindings",
            sa.Column("id", UUID, primary_key=True),
            sa.Column(
                "telegram_chat_id",
                UUID,
                sa.ForeignKey("telegram_chats.id"),
                nullable=False,
            ),
            sa.Column("message_thread_id", sa.BigInteger(), nullable=False),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id")),
            sa.Column("board_id", UUID, sa.ForeignKey("yougile_boards.id")),
            sa.Column("source_name", sa.Text()),
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
            sa.UniqueConstraint(
                "telegram_chat_id",
                "message_thread_id",
                name="uq_telegram_topic_binding",
            ),
        )

    column_columns = _columns("yougile_columns")
    if "synced_at" not in column_columns:
        op.add_column(
            "yougile_columns",
            sa.Column("synced_at", sa.DateTime(timezone=True)),
        )

    event_columns = _columns("sync_events")
    for name, column in (
        ("provider", sa.Column("provider", sa.Text())),
        ("entity_type", sa.Column("entity_type", sa.Text())),
        ("entity_id", sa.Column("entity_id", UUID)),
        ("external_id", sa.Column("external_id", sa.Text())),
        ("message", sa.Column("message", sa.Text())),
    ):
        if name not in event_columns:
            op.add_column("sync_events", column)
    if "action" in event_columns:
        op.alter_column(
            "sync_events",
            "action",
            existing_type=sa.Text(),
            nullable=True,
        )


def downgrade() -> None:
    pass
