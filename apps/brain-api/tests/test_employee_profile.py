# ruff: noqa: E501
from __future__ import annotations

from uuid import uuid4

import pytest
from agentic_pm_test_utils import seed_pm

from brain_api.application.use_cases.agentic_pm import employee_profile_payload
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_employee_profile_returns_tasks_digest_and_achievements(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        session.add(m.TaskModel(id=uuid4(), seq=1, public_id="GC-1", team_id=seeded["team_id"], assignee_id=seeded["employee_id"], title="Mine", status="todo", priority="medium", source="manual"))
        await session.commit()
        payload = await employee_profile_payload(session, seeded["employee_id"], team_id=seeded["team_id"])

    assert payload["stats"]["open_tasks"] == 1
    assert payload["achievements"]
