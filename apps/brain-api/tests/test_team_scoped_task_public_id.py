from uuid import uuid4

import pytest

from brain_api.application.task_numbering import next_task_public_id
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_team_scoped_task_public_id_allows_same_gc_id_per_team(session_factory):
    async with session_factory() as session:
        owner = m.UserModel(id=uuid4(), display_name="Owner")
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=owner.id
        )
        team_a = m.TeamModel(
            id=uuid4(), company_id=company.id, name="A", timezone="Europe/Moscow"
        )
        team_b = m.TeamModel(
            id=uuid4(), company_id=company.id, name="B", timezone="Europe/Moscow"
        )
        session.add_all([owner, company, team_a, team_b])
        await session.flush()

        seq_a, public_a = await next_task_public_id(session, team_a.id)
        seq_b, public_b = await next_task_public_id(session, team_b.id)
        session.add_all([
            m.TaskModel(
                id=uuid4(),
                seq=seq_a,
                public_id=public_a,
                team_id=team_a.id,
                title="A",
                status="todo",
                priority="medium",
                source="manual",
            ),
            m.TaskModel(
                id=uuid4(),
                seq=seq_b,
                public_id=public_b,
                team_id=team_b.id,
                title="B",
                status="todo",
                priority="medium",
                source="manual",
            ),
        ])
        await session.commit()

    assert public_a == "GC-1"
    assert public_b == "GC-1"
