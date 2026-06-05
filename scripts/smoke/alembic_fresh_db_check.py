"""Smoke-check that a fresh PostgreSQL DB migrated by Alembic matches ORM.

Run from the repository root:
    TEST_DATABASE_URL=postgresql+asyncpg://... python scripts/smoke/alembic_fresh_db_check.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

REPO_ROOT = Path(__file__).resolve().parents[2]
BRAIN_API_DIR = REPO_ROOT / "apps" / "brain-api"
SRC_DIR = BRAIN_API_DIR / "src"

sys.path.insert(0, str(SRC_DIR))

from brain_api.infrastructure.db import models as m  # noqa: E402

REQUIRED_COLUMNS = {
    "users": {"email", "display_name"},
    "companies": {"timezone"},
    "teams": {"timezone"},
    "tasks": {"team_id"},
    "task_proposals": {"team_id"},
    "confirmations": {"team_id"},
    "telegram_link_codes": {"used_at"},
    "llm_settings": {"provider"},
    "board_cards": {"team_id"},
}


async def _inspect_database(database_url: str) -> tuple[set[str], dict[str, set[str]]]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(_inspect_sync)
    finally:
        await engine.dispose()


def _inspect_sync(conn) -> tuple[set[str], dict[str, set[str]]]:
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    columns = {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in tables
    }
    return tables, columns


async def _assert_empty_database(database_url: str) -> None:
    tables, _ = await _inspect_database(database_url)
    non_alembic_tables = tables - {"alembic_version"}
    if non_alembic_tables and os.getenv("SMOKE_ALEMBIC_ALLOW_NON_EMPTY") != "1":
        names = ", ".join(sorted(non_alembic_tables))
        raise RuntimeError(
            "Fresh Alembic smoke must run against an empty database. "
            f"Existing tables: {names}"
        )


def _run_alembic(database_url: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    config = Config(str(BRAIN_API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BRAIN_API_DIR / "alembic"))
    config.set_main_option("prepend_sys_path", str(SRC_DIR))
    command.upgrade(config, "head")


async def _assert_schema(database_url: str) -> None:
    tables, columns = await _inspect_database(database_url)
    orm_tables = set(m.Base.metadata.tables)
    missing_tables = sorted(orm_tables - tables)
    if missing_tables:
        raise AssertionError(f"Alembic did not create ORM tables: {missing_tables}")

    missing_columns: dict[str, list[str]] = {}
    for table_name, required in REQUIRED_COLUMNS.items():
        absent = sorted(required - columns.get(table_name, set()))
        if absent:
            missing_columns[table_name] = absent
    if missing_columns:
        raise AssertionError(f"Alembic schema is missing required columns: {missing_columns}")


async def _assert_minimal_insert(database_url: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    now = datetime.now(UTC)
    user_id = uuid4()
    company_id = uuid4()
    team_id = uuid4()

    try:
        async with engine.begin() as conn:
            await conn.execute(
                m.UserModel.__table__.insert().values(
                    id=user_id,
                    email=f"smoke-{user_id.hex}@example.com",
                    display_name="Smoke Director",
                    created_at=now,
                    updated_at=now,
                )
            )
            await conn.execute(
                m.CompanyModel.__table__.insert().values(
                    id=company_id,
                    name="Smoke Company",
                    timezone="Europe/Moscow",
                    created_by=user_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            await conn.execute(
                m.CompanyAdminModel.__table__.insert().values(
                    id=uuid4(),
                    company_id=company_id,
                    user_id=user_id,
                    role="director",
                    created_at=now,
                )
            )
            await conn.execute(
                m.TeamModel.__table__.insert().values(
                    id=team_id,
                    company_id=company_id,
                    name="Smoke Team",
                    timezone="Europe/Moscow",
                    board_provider="yougile",
                    created_at=now,
                    updated_at=now,
                )
            )
            await conn.execute(
                m.TeamMemberModel.__table__.insert().values(
                    id=uuid4(),
                    team_id=team_id,
                    user_id=user_id,
                    role="manager",
                    joined_at=now,
                )
            )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Set TEST_DATABASE_URL or DATABASE_URL for a fresh PostgreSQL DB")
    if not database_url.startswith("postgresql+asyncpg://"):
        raise RuntimeError("Fresh Alembic smoke requires postgresql+asyncpg DATABASE_URL")

    asyncio.run(_assert_empty_database(database_url))
    _run_alembic(database_url)
    asyncio.run(_assert_schema(database_url))
    asyncio.run(_assert_minimal_insert(database_url))
    print("[PASS] Alembic fresh DB schema matches ORM and accepts minimal v2 inserts")


if __name__ == "__main__":
    main()
