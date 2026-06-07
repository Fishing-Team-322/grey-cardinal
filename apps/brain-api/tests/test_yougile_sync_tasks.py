# ruff: noqa: E501
from __future__ import annotations

import pytest
from agentic_pm_test_utils import FullFakeYouGile, seed_pm

from brain_api.application.use_cases.agentic_pm import YouGileFullSyncService
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_yougile_sync_pushes_local_task_without_link(session_factory):
    seeded = await seed_pm(session_factory)
    fake = FullFakeYouGile()
    async with session_factory() as session:
        service = YouGileFullSyncService(session, team_id=seeded["team_id"], cipher=seeded["cipher"], api_base_url="https://fake", client=fake)
        await service.refresh_catalog()
        await service.select_board("b1")
        session.add(m.TaskModel(id=__import__("uuid").uuid4(), seq=99, public_id="GC-99", team_id=seeded["team_id"], title="Local task", status="todo", priority="medium", source="manual"))
        await session.commit()
        summary = await service.sync_selected_board()

    assert summary["outbound"]["created"] >= 1
    assert any(item["title"] == "Local task" for item in fake.created)
