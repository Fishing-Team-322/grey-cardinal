"""finalize identity, inbox, and board mirror tables

Revision ID: 0007_agentic_board_mirror
Revises: 0006_agentic_pm_system
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_agentic_board_mirror"
down_revision = "0006_agentic_pm_system"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def _constraints(table: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in _inspector().get_unique_constraints(table)
        if constraint["name"]
    }


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in _inspector().get_indexes(table)}


def upgrade() -> None:
    tables = set(_inspector().get_table_names())
    chat_columns = _columns("chat_messages")
    for name, column in (
        ("sender_telegram_user_id", sa.Column("sender_telegram_user_id", sa.BigInteger())),
        ("reply_to_message_id", sa.Column("reply_to_message_id", sa.BigInteger())),
        (
            "reply_to_sender_user_id",
            sa.Column("reply_to_sender_user_id", UUID, sa.ForeignKey("users.id")),
        ),
        (
            "reply_to_sender_telegram_user_id",
            sa.Column("reply_to_sender_telegram_user_id", sa.BigInteger()),
        ),
        ("reply_to_text", sa.Column("reply_to_text", sa.Text())),
        ("message_thread_id", sa.Column("message_thread_id", sa.BigInteger())),
    ):
        if name not in chat_columns:
            op.add_column("chat_messages", column)

    if "user_aliases" not in tables:
        op.create_table(
            "user_aliases",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("alias", sa.Text(), nullable=False),
            sa.Column("normalized_alias", sa.Text(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Float(), server_default="1", nullable=False),
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
                "team_id", "normalized_alias", name="uq_user_alias_team_normalized"
            ),
        )
        op.create_index("ix_user_alias_team_user", "user_aliases", ["team_id", "user_id"])

    if "ai_inbox_items" not in tables:
        _create_ai_inbox()
    else:
        columns = _columns("ai_inbox_items")
        for old, new in (
            ("item_type", "kind"),
            ("source_text", "raw_text"),
            ("parsed_payload", "semantic_payload"),
            ("linked_task_id", "duplicate_task_id"),
        ):
            if old in columns and new not in columns:
                op.alter_column("ai_inbox_items", old, new_column_name=new)
        columns = _columns("ai_inbox_items")
        if "source_message_id" not in columns:
            op.add_column("ai_inbox_items", sa.Column("source_message_id", UUID))
            op.create_foreign_key(
                "fk_ai_inbox_source_message",
                "ai_inbox_items",
                "chat_messages",
                ["source_message_id"],
                ["id"],
            )
        if "reason" not in columns:
            op.add_column(
                "ai_inbox_items",
                sa.Column("reason", sa.Text(), server_default="legacy_import", nullable=False),
            )
        if "identity_payload" not in columns:
            op.add_column("ai_inbox_items", sa.Column("identity_payload", JSONB))
        if "ix_ai_inbox_team_status_created" not in _indexes("ai_inbox_items"):
            op.create_index(
                "ix_ai_inbox_team_status_created",
                "ai_inbox_items",
                ["team_id", "status", "created_at"],
            )

    if "yougile_connections" not in tables:
        _create_yougile_connections()
    else:
        columns = _columns("yougile_connections")
        if "external_company_id" not in columns:
            op.add_column(
                "yougile_connections",
                sa.Column(
                    "external_company_id", sa.Text(), server_default="", nullable=False
                ),
            )
        if "company_name" not in columns:
            op.add_column("yougile_connections", sa.Column("company_name", sa.Text()))
        if "credentials_encrypted" in columns:
            op.alter_column(
                "yougile_connections",
                "credentials_encrypted",
                existing_type=sa.LargeBinary(),
                nullable=True,
            )
        if "uq_yougile_connection_team" not in _constraints("yougile_connections"):
            op.create_unique_constraint(
                "uq_yougile_connection_team", "yougile_connections", ["team_id"]
            )

    if "yougile_boards" not in tables:
        _create_yougile_boards()
    else:
        op.alter_column(
            "yougile_boards", "connection_id", existing_type=UUID, nullable=True
        )
        op.alter_column(
            "yougile_boards",
            "synced_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
        if "uq_yougile_board_team_external" not in _constraints("yougile_boards"):
            op.create_unique_constraint(
                "uq_yougile_board_team_external",
                "yougile_boards",
                ["team_id", "external_id"],
            )
        if "ix_yougile_board_selected" not in _indexes("yougile_boards"):
            op.create_index(
                "ix_yougile_board_selected",
                "yougile_boards",
                ["team_id", "is_selected"],
            )

    if "yougile_columns" not in tables:
        _create_yougile_columns()
    else:
        op.execute("UPDATE yougile_columns SET position = 0 WHERE position IS NULL")
        op.alter_column(
            "yougile_columns",
            "position",
            existing_type=sa.Integer(),
            server_default="0",
            nullable=False,
        )
        columns = _columns("yougile_columns")
        if "synced_at" in columns:
            op.alter_column(
                "yougile_columns",
                "synced_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=True,
            )
        if "ix_yougile_column_status" not in _indexes("yougile_columns"):
            op.create_index(
                "ix_yougile_column_status",
                "yougile_columns",
                ["board_id", "mapped_status"],
            )

    if "external_task_links" not in tables:
        _create_external_task_links()
    else:
        columns = _columns("external_task_links")
        op.execute(
            "UPDATE external_task_links SET external_board_id = '' "
            "WHERE external_board_id IS NULL"
        )
        op.alter_column(
            "external_task_links",
            "external_board_id",
            existing_type=sa.Text(),
            nullable=False,
        )
        for name in ("created_at", "updated_at"):
            if name not in columns:
                op.add_column(
                    "external_task_links",
                    sa.Column(
                        name,
                        sa.DateTime(timezone=True),
                        server_default=sa.func.now(),
                        nullable=False,
                    ),
                )
        if "uq_external_task_local" not in _constraints("external_task_links"):
            op.create_unique_constraint(
                "uq_external_task_local",
                "external_task_links",
                ["team_id", "task_id", "provider"],
            )
        if "ix_external_task_team_sync" not in _indexes("external_task_links"):
            op.create_index(
                "ix_external_task_team_sync",
                "external_task_links",
                ["team_id", "sync_status"],
            )

    if "sync_events" not in tables:
        _create_sync_events()
    else:
        columns = _columns("sync_events")
        for name, column in (
            ("task_id", sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"))),
            (
                "link_id",
                sa.Column(
                    "link_id", UUID, sa.ForeignKey("external_task_links.id")
                ),
            ),
            (
                "action",
                sa.Column("action", sa.Text(), server_default="sync", nullable=False),
            ),
            ("error", sa.Column("error", sa.Text())),
        ):
            if name not in columns:
                op.add_column("sync_events", column)
        for name in ("provider", "entity_type"):
            if name in columns:
                op.alter_column(
                    "sync_events", name, existing_type=sa.Text(), nullable=True
                )
        if "ix_sync_event_team_created" not in _indexes("sync_events"):
            op.create_index(
                "ix_sync_event_team_created", "sync_events", ["team_id", "created_at"]
            )

    op.execute(
        """
        INSERT INTO external_task_links (
            id, team_id, task_id, provider, external_board_id, external_column_id,
            external_task_id, external_url, last_synced_at, sync_status, raw_payload,
            created_at, updated_at
        )
        SELECT
            bc.id, bc.team_id, bc.task_id, bc.provider,
            COALESCE(ym.payload->>'boardId', ''), ym.payload->>'columnId',
            bc.external_card_id, bc.external_url, ym.last_synced_at, 'synced',
            COALESCE(ym.payload, bc.external_payload), bc.created_at, bc.updated_at
        FROM board_cards bc
        LEFT JOIN yougile_mappings ym
          ON ym.team_id = bc.team_id
         AND ym.entity_type = 'task'
         AND ym.yougile_id = bc.external_card_id
        WHERE bc.team_id IS NOT NULL
          AND bc.external_card_id <> ''
        ON CONFLICT DO NOTHING
        """
    )


def _create_ai_inbox() -> None:
    op.create_table(
        "ai_inbox_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("source_message_id", UUID, sa.ForeignKey("chat_messages.id")),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("semantic_payload", JSONB),
        sa.Column("identity_payload", JSONB),
        sa.Column("duplicate_task_id", UUID, sa.ForeignKey("tasks.id")),
        sa.Column("confidence", sa.Float(), nullable=False),
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
    op.create_index(
        "ix_ai_inbox_team_status_created",
        "ai_inbox_items",
        ["team_id", "status", "created_at"],
    )


def _create_yougile_connections() -> None:
    op.create_table(
        "yougile_connections",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("external_company_id", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text()),
        sa.Column("status", sa.Text(), server_default="connected", nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
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
        sa.UniqueConstraint("team_id", name="uq_yougile_connection_team"),
    )


def _create_yougile_boards() -> None:
    op.create_table(
        "yougile_boards",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("connection_id", UUID, sa.ForeignKey("yougile_connections.id")),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_selected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("raw_payload", JSONB),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "team_id", "external_id", name="uq_yougile_board_team_external"
        ),
    )
    op.create_index(
        "ix_yougile_board_selected", "yougile_boards", ["team_id", "is_selected"]
    )


def _create_yougile_columns() -> None:
    op.create_table(
        "yougile_columns",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("board_id", UUID, sa.ForeignKey("yougile_boards.id"), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("mapped_status", sa.Text()),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("raw_payload", JSONB),
        sa.UniqueConstraint(
            "board_id", "external_id", name="uq_yougile_column_board_external"
        ),
    )
    op.create_index(
        "ix_yougile_column_status", "yougile_columns", ["board_id", "mapped_status"]
    )


def _create_external_task_links() -> None:
    op.create_table(
        "external_task_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_board_id", sa.Text(), nullable=False),
        sa.Column("external_column_id", sa.Text()),
        sa.Column("external_task_id", sa.Text(), nullable=False),
        sa.Column("external_url", sa.Text()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("sync_status", sa.Text(), server_default="local_only", nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("raw_payload", JSONB),
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
            "provider", "external_task_id", name="uq_external_task_provider_id"
        ),
        sa.UniqueConstraint(
            "team_id", "task_id", "provider", name="uq_external_task_local"
        ),
    )
    op.create_index(
        "ix_external_task_team_sync",
        "external_task_links",
        ["team_id", "sync_status"],
    )


def _create_sync_events() -> None:
    op.create_table(
        "sync_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id")),
        sa.Column("link_id", UUID, sa.ForeignKey("external_task_links.id")),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payload", JSONB),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_sync_event_team_created", "sync_events", ["team_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_alias_team_user", table_name="user_aliases")
    op.drop_table("user_aliases")
    for column in (
        "reply_to_text",
        "reply_to_sender_telegram_user_id",
        "reply_to_sender_user_id",
        "reply_to_message_id",
        "sender_telegram_user_id",
    ):
        op.drop_column("chat_messages", column)
