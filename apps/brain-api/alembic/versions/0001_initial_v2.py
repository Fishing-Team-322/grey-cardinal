"""initial v2 production schema

Revision ID: 0001_initial_v2
Revises:
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_v2"
down_revision = None
branch_labels = None
depends_on = None

UUID = sa.Uuid()
JSONB = postgresql.JSONB(astext_type=sa.Text())


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.Text(), unique=True, nullable=True),
        sa.Column("login", sa.Text(), unique=True, nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), unique=True, nullable=True),
        sa.Column("telegram_username", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("last_name", sa.Text(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=False, server_default=""),
        sa.Column("photo_data_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("role", sa.Text(), nullable=False, server_default="member"),
        sa.Column("timezone", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_table(
        "devices",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", UUID, nullable=True),
        sa.Column("device_name", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("app_version", sa.Text(), nullable=True),
        sa.Column("device_fingerprint", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
    )
    op.create_table(
        "client_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", UUID, sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("workspace_id", UUID, nullable=True),
        sa.Column("session_token_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
    )
    op.create_table(
        "projects",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("default_chat_id", UUID, nullable=True),
        *timestamps(),
    )
    op.create_table(
        "companies",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "company_admins",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role in ('director')", name="ck_company_admin_role"),
        sa.UniqueConstraint("company_id", "user_id", name="uq_company_admin_user"),
    )
    op.create_table(
        "llm_settings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("team_id", UUID, nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("strict_json", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.CheckConstraint("provider in ('local','external_api')", name="ck_llm_provider"),
    )
    op.create_table(
        "teams",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("board_provider", sa.Text(), nullable=False, server_default="yougile"),
        sa.Column("board_credentials_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("board_config", JSONB, nullable=True),
        sa.Column("llm_settings_id", UUID, sa.ForeignKey("llm_settings.id"), nullable=True),
        *timestamps(),
        sa.CheckConstraint("board_provider in ('yougile')", name="ck_team_board_provider"),
    )
    op.create_foreign_key("fk_llm_settings_team", "llm_settings", "teams", ["team_id"], ["id"])
    op.create_table(
        "team_members",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("invited_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role in ('manager','employee')", name="ck_team_member_role"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member_user"),
    )
    op.create_table(
        "invites",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("token", sa.Text(), unique=True, nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("scope in ('company','team')", name="ck_invite_scope"),
        sa.CheckConstraint("role in ('director','manager','employee')", name="ck_invite_role"),
    )
    op.create_table(
        "telegram_link_codes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.Text(), unique=True, nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "telegram_chats",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("tg_chat_id", sa.BigInteger(), unique=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("linked_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_confirmation_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
    )
    op.create_foreign_key("fk_projects_default_chat", "projects", "telegram_chats", ["default_chat_id"], ["id"])
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", UUID, sa.ForeignKey("telegram_chats.id"), nullable=False),
        sa.Column("sender_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("raw_json", JSONB, nullable=False),
        *timestamps(),
        sa.UniqueConstraint("chat_id", "telegram_message_id", name="uq_chat_message"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("seq", sa.Integer(), unique=True, nullable=False),
        sa.Column("public_id", sa.Text(), unique=True, nullable=False),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column("assignee_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assignee_text", sa.Text(), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_timezone", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_message_id", UUID, nullable=True),
        sa.Column("created_from_proposal_id", UUID, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_update_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("status in ('todo','in_progress','blocked','review','done','cancelled')", name="ck_task_status"),
        sa.CheckConstraint("priority in ('low','medium','high','critical')", name="ck_task_priority"),
    )
    op.create_table(
        "task_proposals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_message_id", UUID, sa.ForeignKey("chat_messages.id"), nullable=True),
        sa.Column("source_transcript_id", UUID, nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assignee_text", sa.Text(), nullable=True),
        sa.Column("assignee_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_timezone", sa.Text(), nullable=True),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("extractor_payload", JSONB, nullable=False),
        sa.Column("similar_task_id", UUID, sa.ForeignKey("tasks.id"), nullable=True),
        *timestamps(),
    )
    op.create_foreign_key("fk_task_created_from_proposal", "tasks", "task_proposals", ["created_from_proposal_id"], ["id"])
    op.create_table(
        "confirmations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("proposal_id", UUID, sa.ForeignKey("task_proposals.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_task_id", UUID, sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("status in ('pending','accepted','rejected','expired')", name="ck_confirmation_status"),
    )
    op.create_table(
        "meetings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("seq", sa.Integer(), unique=True, nullable=False),
        sa.Column("public_id", sa.Text(), unique=True, nullable=False),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("telegram_chat_id", UUID, sa.ForeignKey("telegram_chats.id"), nullable=True),
        sa.Column("external_source", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_timezone", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("source_message_id", UUID, nullable=True),
        sa.Column("poll_message_id", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        *timestamps(),
    )
    op.create_table(
        "meeting_participants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("meeting_id", UUID, sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", UUID, sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("client_session_id", UUID, sa.ForeignKey("client_sessions.id"), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        *timestamps(),
        sa.UniqueConstraint("meeting_id", "user_id", name="uq_meeting_participant_user"),
    )
    op.create_table(
        "meeting_rsvp",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("meeting_id", UUID, sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("meeting_id", "user_id", name="uq_meeting_rsvp_user"),
    )
    op.create_table(
        "transcript_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("meeting_db_id", UUID, sa.ForeignKey("meetings.id"), nullable=True),
        sa.Column("meeting_id", sa.Text(), nullable=True),
        sa.Column("speaker_id", sa.Text(), nullable=True),
        sa.Column("speaker_name", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("raw_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "daily_sync_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("status in ('open','closed')", name="ck_daily_sync_session_status"),
    )
    op.create_table(
        "daily_sync_reports",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("sync_session_id", UUID, sa.ForeignKey("daily_sync_sessions.id"), nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("telegram_message_id", UUID, nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("parsed_summary", sa.Text(), nullable=True),
        sa.Column("matched_task_id", UUID, sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("detected_status", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("detected_status in ('done','in_progress','blocked','unknown')", name="ck_daily_sync_report_status"),
    )
    op.create_table(
        "absence_periods",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_message_id", UUID, nullable=True),
        *timestamps(),
        sa.CheckConstraint("status in ('active','expired','cancelled')", name="ck_absence_status"),
    )
    op.create_table(
        "board_cards",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), unique=True, nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_card_id", sa.Text(), nullable=False),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("external_payload", JSONB, nullable=True),
        *timestamps(),
    )
    op.create_table(
        "reminder_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("recipient_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("recipient_telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
    )
    op.create_table(
        "digest_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
    )
    op.create_table(
        "gamification_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("team_id", UUID, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("xp_delta", sa.Integer(), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", UUID, nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "user_xp_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", UUID, nullable=True),
        sa.Column("task_id", UUID, sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("meeting_id", UUID, sa.ForeignKey("meetings.id"), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "user_xp_totals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", UUID, nullable=True),
        sa.Column("points_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "workspace_id", name="uq_user_xp_total_scope"),
    )
    op.create_table(
        "organizations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("photo_data_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "organization_members",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("role", sa.Text(), nullable=False, server_default="member"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("invited_email", sa.Text(), nullable=True),
        sa.Column("invite_token", sa.Text(), unique=True, nullable=True),
        *timestamps(),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member_user"),
    )


def downgrade() -> None:
    for table in (
        "audit_logs",
        "gamification_events",
        "organization_members",
        "organizations",
        "user_xp_totals",
        "user_xp_events",
        "digest_logs",
        "reminder_logs",
        "board_cards",
        "absence_periods",
        "daily_sync_reports",
        "daily_sync_sessions",
        "transcript_events",
        "meeting_rsvp",
        "meeting_participants",
        "meetings",
        "confirmations",
        "task_proposals",
        "tasks",
        "chat_messages",
        "telegram_chats",
        "telegram_link_codes",
        "invites",
        "team_members",
        "teams",
        "llm_settings",
        "company_admins",
        "companies",
        "users",
    ):
        op.drop_table(table)
