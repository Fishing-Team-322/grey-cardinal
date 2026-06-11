"""Тесты симуляции проекта на команду (Bucket B killer-feature)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from brain_api.application.use_cases import project_simulation as ps
from brain_api.application.use_cases.project_simulation import (
    MemberCapacity,
    WorkItem,
    heuristic_decompose,
    simulate,
)
from brain_api.infrastructure.db import models as m

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


# ── Decomposition ─────────────────────────────────────────────────────────────


def test_heuristic_decompose_splits_and_assigns_roles():
    items = heuristic_decompose("интеграция оплаты, личный кабинет, мобильное приложение")
    assert len(items) == 3
    roles = {i.role for i in items}
    assert "backend" in roles  # «интеграция оплаты»
    assert "mobile" in roles   # «мобильное приложение»
    assert all(i.hours > 0 for i in items)


def test_heuristic_decompose_empty():
    assert heuristic_decompose("") == []


# ── Pure simulate ─────────────────────────────────────────────────────────────


def _cap(name, role, active=1, stress=0.0, weekly=30.0):
    return MemberCapacity(
        user_id=uuid4(), display_name=name, role=role, active_count=active,
        stress=stress, weekly_capacity_hours=weekly,
    )


def test_simulate_fits_when_capacity_ample():
    items = [WorkItem("API", "backend", 40), WorkItem("UI", "frontend", 40)]
    caps = [
        _cap("Аня", "backend", active=0, weekly=30),
        _cap("Петя", "frontend", active=0, weekly=30),
    ]
    res = simulate(items, caps, current_mood=0.7, horizon_weeks=4)
    assert res.verdict == "fits"
    assert res.budget_min > 0 and res.budget_max >= res.budget_min
    assert res.projected_mood >= res.current_mood - 0.1


def test_simulate_hire_needed_when_role_missing():
    items = [WorkItem("ML модель", "ml", 200)]
    caps = [_cap("Петя", "frontend", weekly=30)]
    res = simulate(items, caps, current_mood=0.7, horizon_weeks=4)
    assert res.verdict == "hire_needed"
    assert "ml" in res.missing_roles
    assert any("ml" in r.lower() for r in res.recommendations)


def test_simulate_mood_drops_under_overload():
    items = [WorkItem("Большая интеграция", "backend", 400)]
    caps = [_cap("Аня", "backend", active=5, stress=0.7, weekly=12)]
    res = simulate(items, caps, current_mood=0.7, horizon_weeks=4)
    assert res.projected_mood < res.current_mood
    assert res.verdict in {"tight", "hire_needed"}
    assert len(res.mood_trajectory) == 5  # стартовое + 4 недели
    assert any("настроение" in r.lower() or "перегруж" in r.lower() for r in res.risks)


def test_simulation_result_serializable():
    items = [WorkItem("API", "backend", 40)]
    caps = [_cap("Аня", "backend", weekly=30)]
    res = simulate(items, caps, current_mood=0.6, horizon_weeks=3)
    d = res.to_dict()
    assert isinstance(d["work_items"], list) and isinstance(d["member_projections"], list)
    assert d["work_items"][0]["role"] == "backend"


# ── End-to-end with DB ────────────────────────────────────────────────────────


async def test_simulate_project_from_db(session_factory):
    async with session_factory() as session:
        director = m.UserModel(id=uuid4(), display_name="Dir")
        anya = m.UserModel(id=uuid4(), display_name="Аня", bio="backend разработчик")
        petya = m.UserModel(id=uuid4(), display_name="Петя", bio="frontend")
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
        # немного нагрузки и стресса у Ани
        for i in range(2):
            session.add(m.TaskModel(
                id=uuid4(), seq=i + 1, public_id=f"GC-{i+1}", team_id=team.id, title="t",
                status="todo", priority="medium", source="telegram_chat", assignee_id=anya.id,
            ))
        session.add(m.EmotionSignalModel(
            id=uuid4(), team_id=team.id, user_id=anya.id, source="chat_text",
            valence=-0.5, stress=0.7, confidence=0.6,
        ))
        await session.commit()

        result = await ps.simulate_project(
            session, team.id, "интеграция оплаты, личный кабинет", horizon_weeks=4, now=NOW,
        )
    assert result.verdict in {"fits", "tight", "hire_needed"}
    assert result.total_hours > 0
    assert len(result.member_projections) == 2
    assert 0.0 <= result.projected_mood <= 1.0


def test_render_simulation_text():
    items = [WorkItem("API", "backend", 40)]
    caps = [_cap("Аня", "backend", weekly=30)]
    res = simulate(items, caps, current_mood=0.6, horizon_weeks=4)
    text = ps.render_simulation_text(res, project_name="Тест")
    assert "Расчёт" in text and "Бюджет" in text and "Настроение" in text


# ── Multi-scenario planner ────────────────────────────────────────────────────


async def _seed_team_with_history(session):
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
    # История: Аня закрывала backend-задачи, Петя — frontend.
    seq = 0
    for title in ("сделать API оплаты", "интеграция с сервером", "endpoint задач"):
        seq += 1
        session.add(m.TaskModel(
            id=uuid4(), seq=seq, public_id=f"GC-{seq}", team_id=team.id, title=title,
            status="done", priority="medium", source="telegram_chat", assignee_id=anya.id,
        ))
    for title in ("вёрстка страницы", "интерфейс кабинета"):
        seq += 1
        session.add(m.TaskModel(
            id=uuid4(), seq=seq, public_id=f"GC-{seq}", team_id=team.id, title=title,
            status="done", priority="medium", source="telegram_chat", assignee_id=petya.id,
        ))
    await session.commit()
    return team.id, anya.id


async def test_skill_matrix_from_history(session_factory):
    async with session_factory() as session:
        team_id, anya_id = await _seed_team_with_history(session)
        matrix = await ps.member_skill_matrix(session, team_id)
    assert anya_id in matrix
    assert matrix[anya_id].get("backend", 0) > 0  # Аня — backend по истории


async def test_plan_project_scenarios(session_factory):
    async with session_factory() as session:
        team_id, _ = await _seed_team_with_history(session)
        # Большой проект → текущего штаба не хватит → появятся сценарии.
        plan = await ps.plan_project(
            session, team_id,
            "огромная интеграция оплаты, ML модель рекомендаций, мобильное приложение",
            horizon_weeks=2, now=NOW,
        )
    assert "current" in plan["scenarios"]
    assert plan["recommended"] in plan["scenarios"]
    assert isinstance(plan["can_use_current_team"], bool)
    # Скилл-матрица отражает роли из истории.
    assert "Аня" in plan["skill_matrix"]


async def test_render_plan_text(session_factory):
    async with session_factory() as session:
        team_id, _ = await _seed_team_with_history(session)
        plan = await ps.plan_project(
            session, team_id, "ML модель, мобильное приложение, интеграция оплаты",
            horizon_weeks=2, now=NOW,
        )
    text = ps.render_plan_text(plan, project_name="Большой проект")
    assert "План проекта" in text and "Текущий штаб" in text
    assert "Хватит текущего штаба" in text
