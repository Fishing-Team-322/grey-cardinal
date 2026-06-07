"""compatibility marker for the first production agentic PM migration

Revision ID: 0006_agentic_pm_system
Revises: 0005_team_board_provider_mock
Create Date: 2026-06-07

The original production revision created an early version of the YouGile mirror
tables. It is intentionally represented as a marker here; revision 0007 detects
whether those tables exist and either upgrades them in place or creates the
final schema on a fresh database.
"""

from __future__ import annotations

revision = "0006_agentic_pm_system"
down_revision = "0005_team_board_provider_mock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
