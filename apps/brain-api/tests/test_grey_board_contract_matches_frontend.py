from uuid import uuid4

import pytest

from brain_api.api.routes.grey_board import grey_board
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_grey_board_contract_matches_frontend(session_factory):
    async with session_factory() as session:
        user = m.UserModel(id=uuid4(), display_name="Manager", email="m@example.com")
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=user.id
        )
        team = m.TeamModel(
            id=uuid4(), company_id=company.id, name="Team", timezone="Europe/Moscow"
        )
        task = m.TaskModel(
            id=uuid4(),
            seq=1,
            public_id="GC-1",
            team_id=team.id,
            title="Task",
            status="todo",
            priority="medium",
            source="manual",
        )
        session.add_all([
            user,
            company,
            team,
            m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=user.id, role="manager"),
            task,
        ])
        await session.commit()

        payload = await grey_board(team.id, user, session, "agent")

    assert payload["team_id"] == str(team.id)
    assert payload["view"] == "agent"
    assert set(payload) >= {"health", "stats", "columns", "recommendations", "generated_at"}
    assert {"tasks", "overdue", "risks", "sync_errors", "ai_inbox"} <= set(payload["stats"])
    assert all({"id", "title", "cards"} <= set(column) for column in payload["columns"])
