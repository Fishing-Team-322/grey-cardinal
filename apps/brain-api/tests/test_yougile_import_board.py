# ruff: noqa: E501
from __future__ import annotations

import pytest
from agentic_pm_test_utils import FullFakeYouGile, seed_pm
from sqlalchemy import select

from brain_api.application.use_cases.agentic_pm import YouGileFullSyncService
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_yougile_import_board_creates_local_task_and_external_link(session_factory):
    seeded = await seed_pm(session_factory)
    fake = FullFakeYouGile()
    async with session_factory() as session:
        service = YouGileFullSyncService(
            session,
            team_id=seeded["team_id"],
            cipher=seeded["cipher"],
            api_base_url="https://fake",
            client=fake,
        )
        await service.refresh_catalog()
        await service.select_board("b1")
        summary = await service.import_selected_board()
        task = await session.scalar(select(m.TaskModel).where(m.TaskModel.title == "Import task"))
        link = await session.scalar(select(m.ExternalTaskLinkModel).where(m.ExternalTaskLinkModel.external_task_id == "yt1"))

    assert summary["imported_tasks"] == 1
    assert task is not None
    assert task.source_type == "yougile_board"
    assert link is not None
    assert link.task_id == task.id
