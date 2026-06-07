# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from agentic_pm_test_utils import seed_pm

from brain_api.application.use_cases.agentic_pm import recommendations_for_team
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_agent_recommendations_detect_overdue_task(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        session.add(m.TaskModel(id=uuid4(), seq=1, public_id="GC-1", team_id=seeded["team_id"], title="Late", status="todo", priority="high", source="manual", deadline=datetime.now(UTC) - timedelta(days=1)))
        await session.commit()
        payload = await recommendations_for_team(session, seeded["team_id"])

    assert any(item["kind"] == "overdue" for item in payload["items"])
