"""YouGileMappingRepo: idempotent upsert + sync-log."""

from __future__ import annotations

from uuid import uuid4

import pytest

from brain_api.infrastructure.db import models as m
from brain_api.integrations.yougile.mappings import YouGileMappingRepo


async def _seed_team(session) -> m.TeamModel:
    user = m.UserModel(id=uuid4(), display_name="U", email="u@e.com", login="u")
    company = m.CompanyModel(id=uuid4(), name="C", timezone="Europe/Moscow", created_by=user.id)
    team = m.TeamModel(
        id=uuid4(), company_id=company.id, name="T", timezone="Europe/Moscow",
        board_provider="yougile",
    )
    session.add_all([user, company, team])
    await session.commit()
    return team


@pytest.mark.asyncio
async def test_upsert_is_idempotent_on_unique_key(session_factory):
    async with session_factory() as session:
        team = await _seed_team(session)
        repo = YouGileMappingRepo(session, team.id)
        await repo.upsert("task", "yg-1", payload={"v": 1})
        await session.commit()
        # Second upsert of the same yougile_id updates, does not duplicate.
        local = uuid4()
        await repo.upsert("task", "yg-1", local_id=local, payload={"v": 2})
        await session.commit()

        rows = await repo.list_by_type("task")
        assert len(rows) == 1
        assert rows[0].payload == {"v": 2}
        assert rows[0].local_id == local
        assert await repo.yougile_id_for_local("task", local) == "yg-1"


@pytest.mark.asyncio
async def test_sync_log_records_event(session_factory):
    async with session_factory() as session:
        team = await _seed_team(session)
        repo = YouGileMappingRepo(session, team.id)
        repo.log(direction="outbound", event="task-pushed", entity_type="task", yougile_id="yg-9")
        await session.commit()

    from sqlalchemy import select
    async with session_factory() as session:
        logs = (await session.execute(select(m.YouGileSyncLogModel))).scalars().all()
        assert len(logs) == 1
        assert logs[0].direction == "outbound"
        assert logs[0].event == "task-pushed"
