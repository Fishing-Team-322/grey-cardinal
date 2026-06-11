"""Тесты стендапа без стендапа + Manager Copilot (Bucket B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from brain_api.application.use_cases import auto_standup as st
from brain_api.application.use_cases import manager_copilot as cp
from brain_api.infrastructure.db import models as m

NOW = datetime(2026, 6, 11, 9, 0, tzinfo=UTC)


async def _seed(session):
    director = m.UserModel(id=uuid4(), display_name="Dir")
    anya = m.UserModel(id=uuid4(), display_name="Аня")
    petya = m.UserModel(id=uuid4(), display_name="Петя")
    session.add_all([director, anya, petya])
    await session.flush()
    company = m.CompanyModel(id=uuid4(), name="A", timezone="UTC", created_by=director.id)
    session.add(company)
    await session.flush()
    team = m.TeamModel(
        id=uuid4(), company_id=company.id, name="Dev", timezone="UTC", board_provider="mock",
    )
    session.add(team)
    await session.flush()
    session.add_all([
        m.TeamMemberModel(team_id=team.id, user_id=anya.id, role="employee"),
        m.TeamMemberModel(team_id=team.id, user_id=petya.id, role="employee"),
    ])
    # Аня: одна в работе, одна заблокирована, одна закрыта вчера.
    session.add_all([
        m.TaskModel(id=uuid4(), seq=1, public_id="GC-1", team_id=team.id, title="API",
                    status="in_progress", priority="medium", source="telegram_chat",
                    assignee_id=anya.id),
        m.TaskModel(id=uuid4(), seq=2, public_id="GC-2", team_id=team.id, title="Блок",
                    status="blocked", priority="medium", source="telegram_chat",
                    assignee_id=anya.id),
        m.TaskModel(id=uuid4(), seq=3, public_id="GC-3", team_id=team.id, title="Готово",
                    status="done", priority="medium", source="telegram_chat",
                    assignee_id=anya.id, completed_at=NOW - timedelta(hours=12)),
    ])
    # Петя: просроченная активная.
    session.add(m.TaskModel(
        id=uuid4(), seq=4, public_id="GC-4", team_id=team.id, title="Просрочка",
        status="todo", priority="medium", source="telegram_chat", assignee_id=petya.id,
        deadline=NOW - timedelta(days=1),
    ))
    await session.commit()
    return team.id


# ── Standup ───────────────────────────────────────────────────────────────────


async def test_build_standup(session_factory):
    async with session_factory() as session:
        team_id = await _seed(session)
        standup = await st.build_standup(session, team_id, now=NOW)
    anya = next(ms for ms in standup.members if ms.display_name == "Аня")
    assert any("GC-1" in d for d in anya.doing)
    assert any("GC-2" in b for b in anya.blocked)
    assert any("GC-3" in d for d in anya.done_recently)
    assert anya.needs_help is True  # заблокирована
    assert standup.total_blocked == 1
    assert "Аня" in standup.needs_help


async def test_render_standup(session_factory):
    async with session_factory() as session:
        team_id = await _seed(session)
        standup = await st.build_standup(session, team_id, now=NOW)
    text = st.render_standup(standup, team_name="Dev")
    assert "стендап" in text.lower() and "Аня" in text and "🆘" in text


def test_render_standup_empty():
    empty = st.TeamStandup(members=[], total_blocked=0, needs_help=[])
    assert "чистый старт" in st.render_standup(empty)


# ── Copilot ───────────────────────────────────────────────────────────────────


async def test_copilot_actions(session_factory):
    async with session_factory() as session:
        team_id = await _seed(session)
        actions = await cp.build_actions(session, team_id, now=NOW)
    kinds = {a.kind for a in actions}
    # Должны быть и просрочка, и разблокировка (в пределах топ-3).
    assert "deadline" in kinds or "unblock" in kinds
    assert len(actions) <= 3
    assert actions == sorted(actions, key=lambda a: a.priority)


async def test_copilot_render(session_factory):
    async with session_factory() as session:
        team_id = await _seed(session)
        text = await cp.copilot_for_manager(session, team_id, now=NOW)
    assert "Копилот" in text


def test_copilot_render_empty():
    assert "горящего нет" in cp.render_copilot([], team_name="Dev")
