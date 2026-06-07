# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from agentic_pm_test_utils import seed_pm

from brain_api.application.use_cases.agentic_pm import (
    employee_profile_payload,
    recommendations_for_team,
)
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_absence_delegation_affects_profile_and_recommendations(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        session.add(m.AbsencePeriodModel(id=uuid4(), team_id=seeded["team_id"], user_id=seeded["employee_id"], delegate_to_user_id=seeded["director_id"], status="active", starts_at=datetime.now(UTC) - timedelta(hours=1), reason="vacation"))
        session.add(m.TaskModel(id=uuid4(), seq=1, public_id="GC-1", team_id=seeded["team_id"], assignee_id=seeded["employee_id"], title="During absence", status="todo", priority="high", source="manual"))
        await session.commit()
        profile = await employee_profile_payload(session, seeded["employee_id"], team_id=seeded["team_id"])
        recs = await recommendations_for_team(session, seeded["team_id"])

    assert profile["absence"]["active"] is True
    assert any(item["kind"] == "absence_risk" for item in recs["items"])
