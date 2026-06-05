"""User web accounts: email, login, password, profile fields.

Revision ID: 0004_user_accounts
Revises: 0003_desktop_first_audio
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_user_accounts"
down_revision = "0003_desktop_first_audio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("login", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("first_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("bio", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("photo_data_url", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("role", sa.Text(), nullable=False, server_default="member"),
    )

    # Unique indices
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_login", "users", ["login"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_login", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    for col in ("role", "photo_data_url", "bio", "last_name", "first_name", "password_hash", "login", "email"):
        op.drop_column("users", col)
