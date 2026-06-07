# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from agentic_pm_test_utils import seed_pm

from brain_api.application.use_cases.agentic_pm import grey_board_payload
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_grey_board_timeline_view_groups_today(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        session.add(m.TaskModel(id=uuid4(), seq=1, public_id="GC-1", team_id=seeded["team_id"], title="Today", status="todo", priority="medium", source="manual", deadline=datetime.now(UTC) + timedelta(minutes=10)))
        await session.commit()
        payload = await grey_board_payload(session, seeded["team_id"], "timeline")

    assert any(group["key"] == "today" and group["cards"] for group in payload["groups"])
