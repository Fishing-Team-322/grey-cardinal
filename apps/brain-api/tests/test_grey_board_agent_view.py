# ruff: noqa: E501
from __future__ import annotations

import pytest
from agentic_pm_test_utils import FullFakeYouGile, seed_pm

from brain_api.application.use_cases.agentic_pm import YouGileFullSyncService, grey_board_payload


@pytest.mark.asyncio
async def test_grey_board_agent_view_has_ai_inbox_and_recommendations(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        service = YouGileFullSyncService(session, team_id=seeded["team_id"], cipher=seeded["cipher"], api_base_url="https://fake", client=FullFakeYouGile())
        await service.refresh_catalog()
        await service.select_board("b1")
        await service.import_selected_board()
        payload = await grey_board_payload(session, seeded["team_id"], "agent")

    assert payload["view"] == "agent"
    assert payload["groups"][0]["key"] == "ai_inbox"
    assert "recommendations" in payload
