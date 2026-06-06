from __future__ import annotations

from uuid import uuid4

from brain_api.application.use_cases.team_gamification import (
    TASK_COMPLETED_XP,
    gamification_profile_payload,
    grant_team_xp,
    team_leaderboard_payload,
)
from brain_api.infrastructure.db import models as m


async def test_team_xp_is_idempotent_and_drives_profile_and_leaderboard(session_factory):
    async with session_factory() as session:
        user = m.UserModel(id=uuid4(), display_name="Closer")
        company = m.CompanyModel(
            id=uuid4(), name="Company", timezone="Europe/Moscow", created_by=user.id
        )
        team = m.TeamModel(
            id=uuid4(), company_id=company.id, name="Core", timezone="Europe/Moscow"
        )
        task = m.TaskModel(
            id=uuid4(),
            seq=1,
            public_id="GC-1",
            team_id=team.id,
            title="Close me",
            status="done",
            priority="medium",
            assignee_id=user.id,
            source="manual",
        )
        session.add_all([user, company, team, task])
        await session.flush()
        session.add(m.TeamMemberModel(team_id=team.id, user_id=user.id, role="employee"))
        await session.flush()

        first = await grant_team_xp(
            session,
            user_id=user.id,
            team_id=team.id,
            task_id=task.id,
            kind="task_completed",
            points=TASK_COMPLETED_XP,
            reason="Закрыл задачу GC-1",
            idempotency_key=f"task_completed:{task.id}",
        )
        repeated = await grant_team_xp(
            session,
            user_id=user.id,
            team_id=team.id,
            task_id=task.id,
            kind="task_completed",
            points=TASK_COMPLETED_XP,
            reason="Закрыл задачу GC-1",
            idempotency_key=f"task_completed:{task.id}",
        )
        profile = await gamification_profile_payload(session, user.id)
        leaderboard = await team_leaderboard_payload(session, team.id)

    assert first is True
    assert repeated is False
    assert profile["points_total"] == TASK_COMPLETED_XP
    assert profile["achievements"][0]["unlocked"] is True
    assert leaderboard["items"][0]["points"] == TASK_COMPLETED_XP
    assert leaderboard["items"][0]["completed_tasks"] == 1
