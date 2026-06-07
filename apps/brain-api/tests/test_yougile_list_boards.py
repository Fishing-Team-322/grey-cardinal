from __future__ import annotations

import pytest
from agentic_pm_test_utils import FullFakeYouGile, seed_pm
from sqlalchemy import select

from brain_api.application.use_cases.agentic_pm import YouGileFullSyncService
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_yougile_catalog_imports_real_board_rows(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        service = YouGileFullSyncService(
            session,
            team_id=seeded["team_id"],
            cipher=seeded["cipher"],
            api_base_url="https://fake",
            client=FullFakeYouGile(),
        )
        stats = await service.refresh_catalog()
        boards = (await session.execute(select(m.YouGileBoardModel))).scalars().all()

    assert stats["boards"] == 1
    assert boards[0].external_id == "b1"
    assert boards[0].name == "Backend Board"
