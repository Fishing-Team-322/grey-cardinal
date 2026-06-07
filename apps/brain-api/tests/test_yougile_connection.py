from __future__ import annotations

import pytest
from agentic_pm_test_utils import FullFakeYouGile, seed_pm

from brain_api.application.use_cases.agentic_pm import YouGileFullSyncService


@pytest.mark.asyncio
async def test_yougile_connection_health_uses_fake_client(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        service = YouGileFullSyncService(
            session,
            team_id=seeded["team_id"],
            cipher=seeded["cipher"],
            api_base_url="https://fake",
            client=FullFakeYouGile(),
        )

        result = await service.check_connection()

    assert result["connected"] is True
    assert result["status"] == "active"
