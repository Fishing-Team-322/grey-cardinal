# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from agentic_pm_test_utils import seed_pm

from brain_api.application.use_cases.agentic_pm import employee_profile_payload
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_employee_profile_returns_tasks_digest_and_achievements(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        completed_at = datetime.now(UTC)
        session.add(
            m.TaskModel(
                id=uuid4(),
                seq=1,
                public_id="GC-1",
                team_id=seeded["team_id"],
                assignee_id=seeded["employee_id"],
                title="Mine",
                status="done",
                priority="medium",
                source="manual",
                completed_at=completed_at,
            )
        )
        await session.commit()
        payload = await employee_profile_payload(session, seeded["employee_id"], team_id=seeded["team_id"])

    assert payload["stats"]["open_tasks"] == 0
    assert payload["tasks"][0]["created_at"]
    assert payload["tasks"][0]["completed_at"] == completed_at.isoformat()
    assert payload["achievements"]
