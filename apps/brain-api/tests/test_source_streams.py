# ruff: noqa: E501
from __future__ import annotations

from uuid import uuid4

import pytest
from agentic_pm_test_utils import seed_pm

from brain_api.application.use_cases.agentic_pm import grey_board_payload
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_source_streams_appear_in_source_view(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        session.add(m.TaskModel(id=uuid4(), seq=1, public_id="GC-1", team_id=seeded["team_id"], title="Topic task", status="todo", priority="medium", source="telegram", source_type="telegram_topic", source_id="42", source_text="source text"))
        await session.commit()
        payload = await grey_board_payload(session, seeded["team_id"], "source")

    assert payload["groups"][0]["key"] == "telegram_topic"
