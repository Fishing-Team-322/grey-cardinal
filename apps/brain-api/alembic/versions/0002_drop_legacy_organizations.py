"""drop legacy organizations / organization_members tables

The flat Organization model was superseded by the unified Company/Team model
(v2_tenants). Fresh databases never create these tables (see 0001_initial_v2),
but databases initialised before the cleanup still have them — drop them here.

Revision ID: 0002_drop_legacy_organizations
Revises: 0001_initial_v2
Create Date: 2026-06-06
"""

from __future__ import annotations

from alembic import op

revision = "0002_drop_legacy_organizations"
down_revision = "0001_initial_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF EXISTS keeps this idempotent on fresh DBs that never had the tables.
    op.execute("DROP TABLE IF EXISTS organization_members")
    op.execute("DROP TABLE IF EXISTS organizations")


def downgrade() -> None:
    # The legacy tables are deliberately not recreated.
    pass
