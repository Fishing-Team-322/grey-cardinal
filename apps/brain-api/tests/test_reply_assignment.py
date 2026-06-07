from uuid import uuid4

import pytest

from brain_api.application.agentic_tasks import IdentityResolver, InteractionMode
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_reply_sender_has_priority_when_task_has_no_name(session_factory):
    async with session_factory() as session:
        owner = m.UserModel(id=uuid4(), display_name="Owner")
        denis = m.UserModel(id=uuid4(), display_name="Денис", telegram_user_id=777)
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=owner.id
        )
        team = m.TeamModel(
            id=uuid4(),
            company_id=company.id,
            name="Team",
            timezone="Europe/Moscow",
            board_provider="mock",
        )
        session.add_all([owner, denis, company, team])
        session.add(
            m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=denis.id, role="employee")
        )
        await session.flush()

        result = await IdentityResolver(session).resolve_assignee(
            team.id,
            None,
            [],
            "сделать до завтра",
            denis.id,
            InteractionMode.REPLY_TASK_COMMAND,
        )

        assert result.user_id == denis.id
        assert result.source == "reply_to_sender"
