"""allow chat_message entity in yougile_mappings (for comment de-duplication)

Revision ID: 0021_yougile_chat_mapping
Revises: 0020_absence_delegate
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_yougile_chat_mapping"
down_revision = "0020_absence_delegate"
branch_labels = None
depends_on = None

CONSTRAINT = "ck_yougile_mapping_entity"
TABLE = "yougile_mappings"
OLD = "entity_type in ('project','board','column','task','user')"
NEW = "entity_type in ('project','board','column','task','user','chat_message')"


def _constraint_exists() -> bool:
    constraints = sa.inspect(op.get_bind()).get_check_constraints(TABLE)
    return any(item.get("name") == CONSTRAINT for item in constraints)


def upgrade() -> None:
    if _constraint_exists():
        op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, NEW)


def downgrade() -> None:
    if _constraint_exists():
        op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, OLD)
