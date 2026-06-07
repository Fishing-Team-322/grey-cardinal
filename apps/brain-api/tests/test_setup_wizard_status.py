from __future__ import annotations

import pytest
from agentic_pm_test_utils import seed_pm

from brain_api.api.routes.agentic_pm import setup_status
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_setup_wizard_status_contains_required_steps(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        user = await session.get(m.UserModel, seeded["director_id"])
        payload = await setup_status(seeded["team_id"], user, session)

    assert [step["key"] for step in payload["steps"]][:2] == ["company", "team"]
    assert any(step["key"] == "yougile" for step in payload["steps"])
