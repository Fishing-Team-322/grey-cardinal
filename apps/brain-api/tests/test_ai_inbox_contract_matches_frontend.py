from uuid import uuid4

import pytest

from brain_api.api.routes.grey_board import ai_inbox
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_ai_inbox_contract_matches_frontend(session_factory):
    async with session_factory() as session:
        user = m.UserModel(id=uuid4(), display_name="Manager", email="m@example.com")
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=user.id
        )
        team = m.TeamModel(
            id=uuid4(), company_id=company.id, name="Team", timezone="Europe/Moscow"
        )
        item = m.AIInboxItemModel(
            id=uuid4(),
            team_id=team.id,
            kind="needs_assignee",
            status="pending",
            reason="ambiguous_assignee",
            raw_text="Denis, do it",
            confidence=0.72,
            source_type="telegram",
            source_id="42",
            proposed_action="choose_assignee",
        )
        session.add_all([
            user,
            company,
            team,
            m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=user.id, role="manager"),
            item,
        ])
        await session.commit()

        payload = await ai_inbox(team.id, user, session)

    assert list(payload) == ["items"]
    expected = {
        "id": str(item.id),
        "kind": "needs_assignee",
        "status": "pending",
        "reason": "ambiguous_assignee",
        "raw_text": "Denis, do it",
        "confidence": 0.72,
        "suggested_action": "choose_assignee",
    }
    assert expected.items() <= payload["items"][0].items()
    assert payload["items"][0]["source"] == {"type": "telegram", "message_id": "42"}
