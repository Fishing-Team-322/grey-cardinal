# ruff: noqa: E501
from __future__ import annotations

from uuid import uuid4

import pytest
from agentic_pm_test_utils import seed_pm

from brain_api.application.use_cases.agentic_pm import ai_inbox_payload
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_ai_inbox_generates_low_confidence_parse_item(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        session.add(m.TaskProposalModel(id=uuid4(), team_id=seeded["team_id"], source="telegram", title="Maybe", priority="medium", confidence=0.5, raw_text="maybe task", extractor_payload={"title": "Maybe"}))
        await session.commit()
        payload = await ai_inbox_payload(session, seeded["team_id"])

    assert payload["items"][0]["type"] == "low_confidence_parse"
