"""Тесты агентного контура заботы: эмоции+загрузка → переброс задач (Bucket B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select

from brain_api.api.routes import internal_telegram as it
from brain_api.application.use_cases.agentic_wellbeing import detect_interventions
from brain_api.infrastructure.db import models as m

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)
TG_CHAT_ID = -100555000222


class FakeContainer:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.board_mirror = SimpleNamespace()


async def _seed(session, *, autonomous=False):
    director = m.UserModel(id=uuid4(), display_name="Dir")
    anya = m.UserModel(id=uuid4(), display_name="Аня", telegram_user_id=7001)
    petya = m.UserModel(id=uuid4(), display_name="Петя", telegram_user_id=7002)
    session.add_all([director, anya, petya])
    await session.flush()
    company = m.CompanyModel(id=uuid4(), name="Acme", timezone="UTC", created_by=director.id)
    session.add(company)
    await session.flush()
    team = m.TeamModel(
        id=uuid4(), company_id=company.id, name="Dev", timezone="UTC", board_provider="mock",
        tg_chat_id=TG_CHAT_ID,
        board_config={"autonomous_mode": True} if autonomous else {},
    )
    session.add(team)
    await session.flush()
    session.add_all([
        m.TeamMemberModel(team_id=team.id, user_id=anya.id, role="employee"),
        m.TeamMemberModel(team_id=team.id, user_id=petya.id, role="employee"),
    ])
    # Аня перегружена: 3 todo-задачи, 2 просрочены.
    for i in range(3):
        deadline = NOW - timedelta(days=1) if i < 2 else NOW + timedelta(days=3)
        session.add(m.TaskModel(
            id=uuid4(), seq=i + 1, public_id=f"GC-{i+1}", team_id=team.id,
            title=f"Задача {i+1}", status="todo", priority="medium",
            source="telegram_chat", assignee_id=anya.id, deadline=deadline,
        ))
    # Петя свободен: 1 задача.
    session.add(m.TaskModel(
        id=uuid4(), seq=4, public_id="GC-4", team_id=team.id, title="Задача 4",
        status="todo", priority="medium", source="telegram_chat", assignee_id=petya.id,
    ))
    # Высокий стресс у Ани.
    for _ in range(3):
        session.add(m.EmotionSignalModel(
            id=uuid4(), team_id=team.id, user_id=anya.id, source="chat_text",
            valence=-0.7, stress=0.8, confidence=0.6,
        ))
    await session.commit()
    return {"team_id": team.id, "anya_id": anya.id, "petya_id": petya.id}


async def test_detect_reassign_overload(session_factory):
    async with session_factory() as session:
        seed = await _seed(session)
        interventions = await detect_interventions(session, seed["team_id"], now=NOW)
    assert len(interventions) >= 1
    iv = interventions[0]
    assert iv.kind == "reassign_overload"
    assert iv.at_risk.user_id == seed["anya_id"]
    assert iv.candidate.user_id == seed["petya_id"]
    assert iv.task_public_id is not None


async def test_detect_suggest_pause_when_no_candidate(session_factory):
    async with session_factory() as session:
        director = m.UserModel(id=uuid4(), display_name="Dir")
        anya = m.UserModel(id=uuid4(), display_name="Аня", telegram_user_id=7001)
        session.add_all([director, anya])
        await session.flush()
        company = m.CompanyModel(id=uuid4(), name="A", timezone="UTC", created_by=director.id)
        session.add(company)
        await session.flush()
        team = m.TeamModel(
            id=uuid4(), company_id=company.id, name="D", timezone="UTC",
            board_provider="mock",
        )
        session.add(team)
        await session.flush()
        session.add(m.TeamMemberModel(team_id=team.id, user_id=anya.id, role="employee"))
        for i in range(2):
            session.add(m.TaskModel(
                id=uuid4(), seq=i + 1, public_id=f"GC-{i+1}", team_id=team.id,
                title="t", status="todo", priority="medium", source="telegram_chat",
                assignee_id=anya.id, deadline=NOW - timedelta(days=1),
            ))
        for _ in range(3):
            session.add(m.EmotionSignalModel(
                id=uuid4(), team_id=team.id, user_id=anya.id, source="chat_text",
                valence=-0.8, stress=0.9, confidence=0.6,
            ))
        await session.commit()
        interventions = await detect_interventions(session, team.id, now=NOW)
    assert len(interventions) == 1
    assert interventions[0].kind == "suggest_pause"
    assert interventions[0].candidate is None


async def test_wellbeing_actions_confirmation_mode(session_factory):
    async with session_factory() as session:
        await _seed(session, autonomous=False)
    container = FakeContainer(session_factory)
    resp = await it._wellbeing_actions_for_chat(container, TG_CHAT_ID)
    assert resp.actions
    kb = resp.actions[0].reply_markup["inline_keyboard"]
    assert kb[0][0]["callback_data"].startswith("chatact:confirm:")
    async with session_factory() as session:
        pending = await session.scalar(select(m.PendingChatActionModel))
        assert pending is not None and pending.kind == "reassign"
        assert (pending.payload or {}).get("origin") == "wellbeing"


async def test_wellbeing_actions_autonomous_applies(session_factory):
    async with session_factory() as session:
        seed = await _seed(session, autonomous=True)
    container = FakeContainer(session_factory)
    resp = await it._wellbeing_actions_for_chat(container, TG_CHAT_ID)
    assert any("перекинул" in a.text for a in resp.actions if hasattr(a, "text"))
    async with session_factory() as session:
        # одна из задач Ани теперь у Пети
        petya_tasks = (
            await session.execute(
                select(m.TaskModel).where(m.TaskModel.assignee_id == seed["petya_id"])
            )
        ).scalars().all()
        assert len(petya_tasks) >= 2  # была 1, добавилась переброшенная


async def test_pet_command_renders(session_factory):
    async with session_factory() as session:
        await _seed(session)
    container = FakeContainer(session_factory)
    resp = await it._pet_actions_for_chat(container, TG_CHAT_ID)
    assert resp.actions and "питомец" in resp.actions[0].text.lower()
