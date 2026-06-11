"""Тесты недельного Team Pulse (Bucket B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from brain_api.application.use_cases import team_pulse as tp
from brain_api.infrastructure.db import models as m

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


async def _seed(session):
    director = m.UserModel(id=uuid4(), display_name="Dir")
    anya = m.UserModel(id=uuid4(), display_name="Аня")
    session.add_all([director, anya])
    await session.flush()
    company = m.CompanyModel(id=uuid4(), name="A", timezone="UTC", created_by=director.id)
    session.add(company)
    await session.flush()
    team = m.TeamModel(
        id=uuid4(), company_id=company.id, name="Dev", timezone="UTC", board_provider="mock",
    )
    session.add(team)
    await session.flush()
    session.add(m.TeamMemberModel(team_id=team.id, user_id=anya.id, role="employee"))
    # 3 задачи закрыты на этой неделе, 1 на прошлой
    for i, days in enumerate([1, 2, 3, 9]):
        session.add(m.TaskModel(
            id=uuid4(), seq=i + 1, public_id=f"GC-{i+1}", team_id=team.id, title="t",
            status="done", priority="medium", source="telegram_chat", assignee_id=anya.id,
            completed_at=NOW - timedelta(days=days),
        ))
    # просроченная активная
    session.add(m.TaskModel(
        id=uuid4(), seq=9, public_id="GC-9", team_id=team.id, title="late",
        status="todo", priority="medium", source="telegram_chat", assignee_id=anya.id,
        deadline=NOW - timedelta(days=1),
    ))
    # эмоции этой недели
    session.add(m.EmotionSignalModel(
        id=uuid4(), team_id=team.id, user_id=anya.id, source="chat_text",
        valence=-0.3, stress=0.5, confidence=0.6, created_at=NOW - timedelta(days=1),
    ))
    await session.commit()
    return team.id


async def test_gather_metrics(session_factory):
    async with session_factory() as session:
        team_id = await _seed(session)
        metrics = await tp.gather_metrics(session, team_id, now=NOW)
    assert metrics.completed_this_week == 3
    assert metrics.completed_prev_week == 1
    assert metrics.overdue_now == 1
    assert metrics.top_performer == "Аня"
    assert metrics.valence_now is not None


async def test_render_pulse(session_factory):
    async with session_factory() as session:
        team_id = await _seed(session)
        metrics = await tp.gather_metrics(session, team_id, now=NOW)
    text = tp.render_pulse(metrics, team_name="Dev")
    assert "Team Pulse" in text
    assert "Закрыто за неделю" in text
    assert "Итог" in text


def test_delta_phrase():
    assert "+2" in tp._delta_phrase(5, 3)
    assert "как и неделей" in tp._delta_phrase(3, 3)
