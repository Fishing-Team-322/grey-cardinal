from uuid import uuid4

import pytest

from brain_api.application.agentic_tasks import IdentityResolver, InteractionMode
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_dative_alias_resolves_to_team_member(session_factory):
    async with session_factory() as session:
        owner = m.UserModel(id=uuid4(), display_name="Owner")
        denis = m.UserModel(id=uuid4(), display_name="Денис", telegram_username="denis")
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
            "Денису",
            [],
            "Денису подготовить отчёт",
            None,
            InteractionMode.AUTO_BACKGROUND,
        )

        assert result.status == "resolved"
        assert result.user_id == denis.id
        assert result.source == "alias"


@pytest.mark.asyncio
async def test_unknown_name_is_not_auto_resolved(session_factory):
    async with session_factory() as session:
        owner = m.UserModel(id=uuid4(), display_name="Owner")
        denis = m.UserModel(id=uuid4(), display_name="Денис")
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
            "Пенис",
            [],
            "Пенис сделай задачу",
            None,
            InteractionMode.AUTO_BACKGROUND,
        )

        assert result.status == "unresolved"
        assert result.user_id is None
