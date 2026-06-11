"""Тесты движка настроения и командного питомца (Bucket B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from brain_api.application import team_mood as tm
from brain_api.application.use_cases import team_pet as tp
from brain_api.application.use_cases.team_settings import (
    EMOTION_ANALYSIS_SETTING,
    emotion_analysis_enabled,
)
from brain_api.infrastructure.db import models as m

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


# ── Pure mood engine ──────────────────────────────────────────────────────────


def test_compute_mood_sad_vs_happy():
    sad = tm.compute_mood(
        tm.MoodInputs(emotion_valence=-0.8, emotion_stress=0.7, task_health=0.2,
                      overdue_pressure=0.8, activity=0.0)
    )
    happy = tm.compute_mood(
        tm.MoodInputs(emotion_valence=0.8, emotion_stress=0.0, task_health=1.0,
                      overdue_pressure=0.0, activity=1.0)
    )
    assert sad < 0.35 < happy
    assert 0.0 <= sad <= 1.0 and 0.0 <= happy <= 1.0


def test_compute_mood_without_emotion_uses_tasks_only():
    # Эмоции выключены (None) → считаем только по задачам, всё ещё работает.
    good = tm.compute_mood(tm.MoodInputs(task_health=1.0, overdue_pressure=0.0, activity=0.8))
    bad = tm.compute_mood(tm.MoodInputs(task_health=0.1, overdue_pressure=0.9))
    assert good > bad


def test_pet_state_transitions():
    assert tm.pet_state(0.9, 0.8) == "happy"
    assert tm.pet_state(0.6, 0.6) == "content"
    assert tm.pet_state(0.45, 0.6) == "neutral"
    assert tm.pet_state(0.2, 0.6) == "sad"
    assert tm.pet_state(0.9, 0.1) == "tired"  # энергия перебивает


def test_decay_energy():
    assert tm.decay_energy(1.0, 24) < 1.0
    assert tm.decay_energy(1.0, 0) == 1.0
    assert tm.decay_energy(0.1, 240) == 0.0  # не уходит ниже нуля


def test_heuristic_affect():
    assert tm.heuristic_affect("спасибо, огонь, получилось!")[0] > 0
    val, stress = tm.heuristic_affect("всё горит, аврал, я выгорел")
    assert val < 0 and stress > 0
    assert tm.heuristic_affect("обычный текст без эмоций") is None


# ── DB use cases ──────────────────────────────────────────────────────────────


async def _seed_team(session, *, emotion_enabled=False):
    director = m.UserModel(id=uuid4(), display_name="Dir")
    session.add(director)
    await session.flush()
    company = m.CompanyModel(
        id=uuid4(), name="Acme", timezone="UTC", created_by=director.id
    )
    session.add(company)
    await session.flush()
    board_config = {}
    if emotion_enabled:
        board_config[EMOTION_ANALYSIS_SETTING] = {"enabled": True, "sources": {"chat_text": True}}
    team = m.TeamModel(
        id=uuid4(), company_id=company.id, name="Dev", timezone="UTC",
        board_provider="mock", board_config=board_config,
    )
    session.add(team)
    await session.flush()
    return team


async def test_emotion_opt_in_gating(session_factory):
    async with session_factory() as session:
        off = await _seed_team(session, emotion_enabled=False)
        on = await _seed_team(session, emotion_enabled=True)
    assert emotion_analysis_enabled(off) is False
    assert emotion_analysis_enabled(on) is True
    assert emotion_analysis_enabled(on, "chat_text") is True
    assert emotion_analysis_enabled(on, "call_video") is False  # не включён явно


async def test_record_signal_and_mood_inputs(session_factory):
    async with session_factory() as session:
        team = await _seed_team(session, emotion_enabled=True)
        for v, s in [(-0.6, 0.7), (-0.4, 0.5), (0.2, 0.1)]:
            await tp.record_emotion_signal(
                session, team_id=team.id, user_id=None, source="chat_text",
                valence=v, stress=s,
            )
        await session.commit()
        inputs = await tp.mood_inputs(session, team.id, now=NOW)
    assert inputs.emotion_valence is not None
    assert inputs.emotion_valence < 0  # средний негатив
    assert inputs.emotion_stress > 0


async def test_pet_payload_sad_when_team_struggling(session_factory):
    async with session_factory() as session:
        team = await _seed_team(session, emotion_enabled=True)
        # Негативные эмоции + просроченная задача → грустный питомец.
        for _ in range(3):
            await tp.record_emotion_signal(
                session, team_id=team.id, user_id=None, source="chat_text",
                valence=-0.8, stress=0.8,
            )
        session.add(
            m.TaskModel(
                id=uuid4(), seq=1, public_id="GC-1", team_id=team.id, title="t",
                status="todo", priority="medium", source="telegram_chat",
                deadline=NOW - timedelta(days=2),
            )
        )
        await session.commit()
        from brain_api.application.use_cases.team_pet_service import build_pet_payload

        payload = await build_pet_payload(session, team.id, now=NOW)
        await session.commit()
    assert payload["state"] in {"sad", "tired"}
    assert payload["mood"] < 0.4
    assert payload["breakdown"]["emotion_available"] is True


async def test_feed_pet_raises_energy_and_xp(session_factory):
    async with session_factory() as session:
        team = await _seed_team(session)
        pet = await tp.ensure_pet(session, team.id)
        pet.energy = 0.3
        await session.flush()
        fed = await tp.feed_pet(session, team.id, energy_gain=0.2, xp_gain=120, now=NOW)
        await session.commit()
    assert fed.energy == 0.5
    assert fed.xp == 120
    assert fed.level == 2  # 120 xp → уровень 2


async def test_recompute_applies_decay(session_factory):
    async with session_factory() as session:
        team = await _seed_team(session)
        pet = await tp.ensure_pet(session, team.id)
        pet.energy = 1.0
        pet.last_decay_at = NOW - timedelta(days=2)
        await session.flush()
        recomputed = await tp.recompute_pet(session, team.id, now=NOW)
        await session.commit()
    assert recomputed.energy < 1.0  # энергия упала за 2 дня


_TG_SEQ = [8000]


async def _seed_user_and_message(session, team):
    _TG_SEQ[0] += 1
    n = _TG_SEQ[0]
    user = m.UserModel(id=uuid4(), display_name="Петя", telegram_user_id=n)
    session.add(user)
    await session.flush()
    chat = m.TelegramChatModel(
        id=uuid4(), team_id=team.id, telegram_chat_id=-100000 - n, type="supergroup"
    )
    session.add(chat)
    await session.flush()
    msg = m.ChatMessageModel(
        id=uuid4(), telegram_message_id=1, chat_id=chat.id, sender_id=user.id,
        text="всё горит, аврал", raw_json={},
    )
    session.add(msg)
    await session.flush()
    return user, msg


async def test_maybe_record_affect_respects_opt_in(session_factory):
    from brain_api.api.routes.internal_telegram import _maybe_record_affect

    # Выключено → сигнал не пишется.
    async with session_factory() as session:
        team = await _seed_team(session, emotion_enabled=False)
        user, msg = await _seed_user_and_message(session, team)
        parsed = {"kind": "noise", "affect": {"valence": -0.5, "stress": 0.6}}
        await _maybe_record_affect(session, team, user, msg, parsed, "всё горит")
        await session.commit()
        count = await session.scalar(
            select(func.count()).select_from(m.EmotionSignalModel)
        )
    assert count == 0

    # Включено → сигнал пишется из affect.
    async with session_factory() as session:
        team = await _seed_team(session, emotion_enabled=True)
        user, msg = await _seed_user_and_message(session, team)
        parsed = {"kind": "noise", "affect": {"valence": -0.5, "stress": 0.6}}
        await _maybe_record_affect(session, team, user, msg, parsed, "всё горит")
        await session.commit()
        signal = await session.scalar(select(m.EmotionSignalModel))
    assert signal is not None
    assert signal.valence == -0.5 and signal.stress == 0.6
    assert signal.source == "chat_text"


async def test_maybe_record_affect_heuristic_fallback(session_factory):
    from brain_api.api.routes.internal_telegram import _maybe_record_affect

    # affect отсутствует → лексический fallback пишет сигнал по тексту.
    async with session_factory() as session:
        team = await _seed_team(session, emotion_enabled=True)
        user, msg = await _seed_user_and_message(session, team)
        parsed = {"kind": "noise", "affect": None}
        await _maybe_record_affect(session, team, user, msg, parsed, "всё горит, аврал, выгорел")
        await session.commit()
        signal = await session.scalar(select(m.EmotionSignalModel))
    assert signal is not None and signal.valence < 0
