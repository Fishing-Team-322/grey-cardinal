"""allow board_provider='mock' (disconnect / auth-failure fallback)

Revision ID: 0005_team_board_provider_mock
Revises: 0004_yougile_integration
Create Date: 2026-06-06
"""

from __future__ import annotations

from alembic import op

revision = "0005_team_board_provider_mock"
down_revision = "0004_yougile_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_team_board_provider", "teams", type_="check")
    op.create_check_constraint(
        "ck_team_board_provider", "teams", "board_provider in ('yougile','mock')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_team_board_provider", "teams", type_="check")
    op.create_check_constraint(
        "ck_team_board_provider", "teams", "board_provider in ('yougile')"
    )
