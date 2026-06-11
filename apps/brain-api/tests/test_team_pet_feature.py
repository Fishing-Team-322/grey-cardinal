"""Тесты фичи «Командный питомец»: create, payload, события, инвентарь,
privacy, scoring, батлы. Хендлеры вызываются напрямую, как в других тестах.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from brain_api.api.routes import team_pet as routes
from brain_api.api.routes.grey_board import team_pet_view
from brain_api.application.use_cases import team_pet_scoring as sc
from brain_api.application.use_cases import team_pet_service as svc
from brain_api.infrastructure.db import models as m

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


async def _seed(session, *, with_employee=False):
    manager = m.UserModel(id=uuid4(), display_name="Manager", email="mgr@example.com")
    company = m.CompanyModel(
        id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=manager.id
    )
    team = m.TeamModel(id=uuid4(), company_id=company.id, name="Growth", timezone="Europe/Moscow")
    rows = [
        manager,
        company,
        team,
        m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=manager.id, role="manager"),
    ]
    employee = None
    if with_employee:
        employee = m.UserModel(id=uuid4(), display_name="Worker", email="w@example.com")
        rows.append(employee)
        rows.append(
            m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=employee.id, role="employee")
        )
    session.add_all(rows)
    await session.commit()
    return manager, employee, team


def _task(team_id, *, status="done", deadline=None, completed_at=None, seq=1, assignee=None):
    return m.TaskModel(
        id=uuid4(),
        seq=seq,
        public_id=f"GC-{seq}",
        team_id=team_id,
        title=f"Task {seq}",
        status=status,
        priority="medium",
        source="manual",
        deadline=deadline,
        completed_at=completed_at,
        assignee_id=assignee,
    )


# ── 1. create ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_team_pet(session_factory):
    async with session_factory() as session:
        manager, _, team = await _seed(session)
        payload = await routes.create_team_pet(
            team.id, routes.CreatePetRequest(name="Фоксик", species="fox"), manager, session
        )
        assert payload["name"] == "Фоксик"
        assert payload["species"] == "fox"
        assert payload["pet"]["species_name"]

        # повторное создание → 409
        with pytest.raises(HTTPException) as exc:
            await routes.create_team_pet(
                team.id, routes.CreatePetRequest(name="X", species="owl"), manager, session
            )
        assert exc.value.status_code == 409

        # событие pet_created есть
        events = await svc.list_events(session, team.id, limit=50)
        assert any(e["event_type"] == "pet_created" for e in events["items"])


@pytest.mark.asyncio
async def test_create_requires_manager(session_factory):
    async with session_factory() as session:
        _, employee, team = await _seed(session, with_employee=True)
        with pytest.raises(HTTPException) as exc:
            await routes.create_team_pet(
                team.id, routes.CreatePetRequest(name="X", species="fox"), employee, session
            )
        assert exc.value.status_code == 403


# ── 2. payload contract ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pet_payload_contract(session_factory):
    async with session_factory() as session:
        manager, _, team = await _seed(session)
        await svc.create_pet(session, team.id, name="Фоксик", species="fox", now=NOW)
        await session.commit()
        payload = await team_pet_view(team.id, manager, session)
        assert {"pet", "metrics", "appearance", "privacy"} <= set(payload)
        # legacy верхнеуровневые поля сохранены
        assert {"name", "species", "mood", "energy", "level", "xp", "state", "emoji", "phrase",
                "breakdown"} <= set(payload)
        assert len(payload["metrics"]) == 6
        assert all({"key", "value", "display", "sparkline", "status"} <= set(c)
                   for c in payload["metrics"])


@pytest.mark.asyncio
async def test_pet_view_404_when_absent(session_factory):
    async with session_factory() as session:
        manager, _, team = await _seed(session)
        with pytest.raises(HTTPException) as exc:
            await team_pet_view(team.id, manager, session)
        assert exc.value.status_code == 404


# ── 3. events feed ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pet_events_feed(session_factory):
    async with session_factory() as session:
        manager, _, team = await _seed(session)
        pet = await svc.create_pet(session, team.id, name="Ф", species="fox", now=NOW)
        await svc.record_event(session, pet, event_type="task_completed_on_time", metric="xp",
                               points_delta=120, reason="6 задач закрыто вовремя",
                               source_type="task", now=NOW + timedelta(hours=1))
        await session.commit()
        feed = await routes.team_pet_events(team.id, manager, session, limit=10)
        assert feed["items"][0]["event_type"] == "task_completed_on_time"
        assert feed["items"][0]["delta"] == "+120 XP"
        assert feed["items"][0]["positive"] is True
        # отсортировано по убыванию времени
        times = [i["created_at"] for i in feed["items"]]
        assert times == sorted(times, reverse=True)


# ── 4. inventory equip ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inventory_equip(session_factory):
    async with session_factory() as session:
        manager, _, team = await _seed(session)
        await svc.create_pet(session, team.id, name="Ф", species="fox", now=NOW)
        await session.commit()

        # locked нельзя надеть
        with pytest.raises(HTTPException) as exc:
            await routes.team_pet_equip(
                team.id, routes.EquipRequest(item_id="champion_helmet"), manager, session
            )
        assert exc.value.status_code == 409

        # owned надевается; предыдущий в категории снимается
        res = await routes.team_pet_equip(
            team.id, routes.EquipRequest(item_id="team_scarf"), manager, session
        )
        assert res["ok"] is True
        scarves = [i for i in res["inventory"]["items"] if i["category"] == "scarf"]
        equipped = [i for i in scarves if i["status"] == "equipped"]
        assert len(equipped) == 1 and equipped[0]["item_id"] == "team_scarf"


# ── 5. privacy ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_privacy_settings(session_factory):
    async with session_factory() as session:
        manager, _, team = await _seed(session)
        await svc.create_pet(session, team.id, name="Ф", species="fox", now=NOW)
        await session.commit()

        default = await routes.get_team_pet_privacy(team.id, manager, session)
        assert default["analyze_calls"] is False
        assert default["analyze_camera"] is False

        saved = await routes.put_team_pet_privacy(
            team.id,
            routes.PrivacyRequest(analyze_chat=False, retention_days=90, visible_to="team"),
            manager,
            session,
        )
        assert saved["analyze_chat"] is False
        assert saved["retention_days"] == 90
        assert saved["visible_to"] == "team"

        # analyze_chat=false блокирует запись новых chat emotion signals
        assert await svc.chat_analysis_allowed(session, team.id) is False


# ── 6. scoring ───────────────────────────────────────────────────────────────


def test_team_pet_scoring_overdue_hurts():
    healthy = sc.compute_scores(sc.ScoringInputs(
        active_count=10, overdue_count=0, done_recent=8, done_prev=4, member_count=4,
        load_values=(3, 2, 3, 2)))
    overdue = sc.compute_scores(sc.ScoringInputs(
        active_count=10, overdue_count=6, done_recent=8, done_prev=4, member_count=4,
        load_values=(3, 2, 3, 2)))
    assert overdue.productivity < healthy.productivity
    assert overdue.stability < healthy.stability
    assert overdue.power < healthy.power


def test_team_pet_scoring_stress_hurts():
    calm = sc.compute_scores(sc.ScoringInputs(
        active_count=5, done_recent=4, member_count=3, emotion_count=10,
        emotion_valence=0.5, emotion_stress=0.1))
    stressed = sc.compute_scores(sc.ScoringInputs(
        active_count=5, done_recent=4, member_count=3, emotion_count=10,
        emotion_valence=-0.5, emotion_stress=0.8))
    assert stressed.communication < calm.communication
    assert stressed.wellbeing < calm.wellbeing
    assert stressed.tension > calm.tension


@pytest.mark.asyncio
async def test_scoring_closed_tasks_raise_power(session_factory):
    async with session_factory() as session:
        manager, _, team = await _seed(session)
        pet = await svc.create_pet(session, team.id, name="Ф", species="fox", now=NOW)
        # много закрытых вовремя задач
        for i in range(6):
            session.add(_task(team.id, status="done", completed_at=NOW - timedelta(days=1),
                              deadline=NOW + timedelta(days=1), seq=i + 1))
        await session.commit()
        scores, _prev, _inp = await sc.recompute_scores(session, pet, now=NOW)
        assert scores.power > 0
        assert scores.productivity >= 60


# ── 7. battle leaderboard ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_battle_leaderboard(session_factory):
    async with session_factory() as session:
        manager, _, team_a = await _seed(session)
        # вторая команда в той же компании
        company_id = team_a.company_id
        team_b = m.TeamModel(id=uuid4(), company_id=company_id, name="Beta",
                             timezone="Europe/Moscow")
        session.add(team_b)
        await session.commit()

        await svc.create_pet(session, team_a.id, name="A", species="fox", now=NOW)
        await svc.create_pet(session, team_b.id, name="B", species="dragon", now=NOW)
        # дать team_a больше закрытых задач → выше power
        for i in range(8):
            session.add(_task(team_a.id, status="done", completed_at=NOW - timedelta(days=1),
                              deadline=NOW + timedelta(days=1), seq=i + 1))
        await session.commit()

        data = await routes.current_battle_leaderboard(manager, session, team_id=team_a.id)
        items = data["items"]
        assert len(items) == 2
        # отсортировано по power_score убыв.
        assert items[0]["power_score"] >= items[1]["power_score"]
        # текущая команда помечена
        current = [i for i in items if i["is_current_team"]]
        assert len(current) == 1 and current[0]["team_id"] == str(team_a.id)
        # ранги проставлены
        assert {i["rank"] for i in items} == {1, 2}
