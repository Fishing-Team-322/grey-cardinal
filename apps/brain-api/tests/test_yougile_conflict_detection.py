# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from agentic_pm_test_utils import FullFakeYouGile, seed_pm
from sqlalchemy import select

from brain_api.application.use_cases.agentic_pm import YouGileFullSyncService
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_yougile_conflict_detection_marks_link_and_inbox(session_factory):
    seeded = await seed_pm(session_factory)
    fake = FullFakeYouGile()
    async with session_factory() as session:
        service = YouGileFullSyncService(session, team_id=seeded["team_id"], cipher=seeded["cipher"], api_base_url="https://fake", client=fake)
        await service.refresh_catalog()
        await service.select_board("b1")
        await service.import_selected_board()
        task = await session.scalar(select(m.TaskModel).where(m.TaskModel.title == "Import task"))
        task.title = "Edited locally"
        task.updated_at = datetime.now(UTC) + timedelta(seconds=1)
        session.add(task)
        await session.commit()
        fake.tasks["c1"][0]["title"] = "Edited in YouGile"
        await service.import_selected_board()
        link = await session.scalar(select(m.ExternalTaskLinkModel).where(m.ExternalTaskLinkModel.external_task_id == "yt1"))
        inbox = await session.scalar(select(m.AiInboxItemModel).where(m.AiInboxItemModel.item_type == "sync_conflict"))

    assert link.sync_status == "conflict"
    assert inbox is not None
