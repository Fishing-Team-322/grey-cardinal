from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from brain_api.api.routes.internal_telegram import TelegramBindTeamRequest, bind_team_chat
from brain_api.api.routes.v2_tenants import create_team_telegram_bind_code
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_bind_team_uses_bind_codes_table(session_factory):
    async with session_factory() as session:
        user = m.UserModel(id=uuid4(), display_name="Manager", email="m@example.com")
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=user.id
        )
        team = m.TeamModel(
            id=uuid4(),
            company_id=company.id,
            name="Team",
            timezone="Europe/Moscow",
            board_config={"theme": "dark"},
        )
        session.add_all([
            user,
            company,
            team,
            m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=user.id, role="manager"),
        ])
        await session.commit()

        response = await create_team_telegram_bind_code(team.id, user, session)
        code_row = await session.scalar(
            select(m.TelegramTeamBindCodeModel).where(
                m.TelegramTeamBindCodeModel.code == response["code"]
            )
        )
        assert code_row is not None
        assert code_row.team_id == team.id
        assert "telegram_bind_code" not in (team.board_config or {})

    container = SimpleNamespace(session_factory=session_factory)
    result = await bind_team_chat(
        TelegramBindTeamRequest(
            code=response["code"],
            tg_chat_id=-100123,
            chat_id=-100123,
            chat_type="supergroup",
            title="Team chat",
        ),
        container,
    )

    assert result.actions
    async with session_factory() as session:
        team = await session.get(m.TeamModel, team.id)
        code_row = await session.scalar(
            select(m.TelegramTeamBindCodeModel).where(
                m.TelegramTeamBindCodeModel.code == response["code"]
            )
        )
        chat = await session.scalar(
            select(m.TelegramChatModel).where(m.TelegramChatModel.telegram_chat_id == -100123)
        )
        assert team.tg_chat_id == -100123
        assert team.board_config == {"theme": "dark"}
        assert code_row.used_at is not None
        assert chat is not None
        assert chat.team_id == team.id
