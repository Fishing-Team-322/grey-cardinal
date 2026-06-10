"""Командный питомец + агрегация эмоций отдела (I/O поверх team_mood)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application import team_mood as tm
from brain_api.infrastructure.db import models as m

ACTIVE_STATUSES = ("todo", "in_progress", "blocked", "review")
EMOTION_WINDOW_DAYS = 7
ACTIVITY_WINDOW_DAYS = 3


async def ensure_pet(session: AsyncSession, team_id: UUID) -> m.TeamPetModel:
    pet = await session.scalar(
        select(m.TeamPetModel).where(m.TeamPetModel.team_id == team_id)
    )
    if pet is None:
        pet = m.TeamPetModel(team_id=team_id)
        session.add(pet)
        await session.flush()
    return pet


async def record_emotion_signal(
    session: AsyncSession,
    *,
    team_id: UUID,
    user_id: UUID | None,
    source: str,
    valence: float,
    arousal: float = 0.0,
    stress: float = 0.0,
    confidence: float = 0.5,
    source_ref: dict[str, Any] | None = None,
) -> m.EmotionSignalModel:
    """Записать производный эмоциональный сигнал (сырьё не храним)."""
    signal = m.EmotionSignalModel(
        team_id=team_id,
        user_id=user_id,
        source=source,
        valence=max(-1.0, min(1.0, float(valence))),
        arousal=max(0.0, min(1.0, float(arousal))),
        stress=max(0.0, min(1.0, float(stress))),
        confidence=max(0.0, min(1.0, float(confidence))),
        source_ref=source_ref,
    )
    session.add(signal)
    await session.flush()
    return signal


async def _emotion_aggregate(
    session: AsyncSession, team_id: UUID, *, now: datetime
) -> tuple[float | None, float | None]:
    since = now - timedelta(days=EMOTION_WINDOW_DAYS)
    row = (
        await session.execute(
            select(
                func.avg(m.EmotionSignalModel.valence),
                func.avg(m.EmotionSignalModel.stress),
                func.count(),
            ).where(
                m.EmotionSignalModel.team_id == team_id,
                m.EmotionSignalModel.created_at >= since,
            )
        )
    ).one()
    valence_avg, stress_avg, count = row
    if not count:
        return None, None
    return float(valence_avg), float(stress_avg)


async def _task_metrics(
    session: AsyncSession, team_id: UUID, *, now: datetime
) -> tuple[float, float, float]:
    """task_health, overdue_pressure, activity ∈ 0..1."""
    active = (
        await session.execute(
            select(m.TaskModel).where(
                m.TaskModel.team_id == team_id,
                m.TaskModel.status.in_(ACTIVE_STATUSES),
            )
        )
    ).scalars().all()
    active_count = len(active)
    overdue = sum(
        1 for t in active if t.deadline is not None and _as_utc(t.deadline) < now
    )
    if active_count:
        overdue_pressure = overdue / active_count
        task_health = 1.0 - overdue_pressure
    else:
        overdue_pressure, task_health = 0.0, 0.7  # пусто = нейтрально-хорошо

    since = now - timedelta(days=ACTIVITY_WINDOW_DAYS)
    closed_recent = int(
        await session.scalar(
            select(func.count()).where(
                m.TaskModel.team_id == team_id,
                m.TaskModel.status == "done",
                m.TaskModel.completed_at.is_not(None),
                m.TaskModel.completed_at >= since,
            )
        )
        or 0
    )
    activity = min(1.0, closed_recent / max(3, active_count or 3))
    return round(task_health, 3), round(overdue_pressure, 3), round(activity, 3)


async def mood_inputs(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> tm.MoodInputs:
    now = now or datetime.now(UTC)
    valence, stress = await _emotion_aggregate(session, team_id, now=now)
    task_health, overdue_pressure, activity = await _task_metrics(session, team_id, now=now)
    return tm.MoodInputs(
        emotion_valence=valence,
        emotion_stress=stress,
        task_health=task_health,
        overdue_pressure=overdue_pressure,
        activity=activity,
    )


async def recompute_pet(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> m.TeamPetModel:
    """Применить decay энергии и пересчитать настроение питомца."""
    now = now or datetime.now(UTC)
    pet = await ensure_pet(session, team_id)
    if pet.last_decay_at is not None:
        hours = (now - _as_utc(pet.last_decay_at)).total_seconds() / 3600.0
        pet.energy = tm.decay_energy(pet.energy, hours)
    pet.last_decay_at = now
    pet.mood = tm.compute_mood(await mood_inputs(session, team_id, now=now))
    pet.level = tm.level_for_pet_xp(pet.xp)
    await session.flush()
    return pet


async def feed_pet(
    session: AsyncSession,
    team_id: UUID,
    *,
    energy_gain: float = 0.12,
    xp_gain: int = 10,
    now: datetime | None = None,
) -> m.TeamPetModel:
    """«Покормить» питомца за командное действие (закрытие задачи, синк)."""
    now = now or datetime.now(UTC)
    pet = await ensure_pet(session, team_id)
    pet.energy = round(max(0.0, min(1.0, pet.energy + energy_gain)), 3)
    pet.xp += xp_gain
    pet.level = tm.level_for_pet_xp(pet.xp)
    pet.last_fed_at = now
    await session.flush()
    return pet


async def pet_payload(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> dict[str, Any]:
    """Готовый payload для mini-app / веб-кабинета / бота."""
    now = now or datetime.now(UTC)
    pet = await recompute_pet(session, team_id, now=now)
    inputs = await mood_inputs(session, team_id, now=now)
    state = tm.pet_state(pet.mood, pet.energy)
    return {
        "team_id": str(team_id),
        "name": pet.name,
        "species": pet.species,
        "mood": pet.mood,
        "energy": pet.energy,
        "level": pet.level,
        "xp": pet.xp,
        "state": state,
        "emoji": tm.state_emoji(state),
        "phrase": tm.state_phrase(state),
        "breakdown": {
            "emotion_valence": inputs.emotion_valence,
            "emotion_stress": inputs.emotion_stress,
            "task_health": inputs.task_health,
            "overdue_pressure": inputs.overdue_pressure,
            "activity": inputs.activity,
            "emotion_available": inputs.emotion_valence is not None,
        },
        "updated_at": now.isoformat(),
    }


def render_pet_line(payload: dict[str, Any]) -> str:
    """Однострочный рендер питомца для чата/дайджеста."""
    return (
        f"{payload['emoji']} {payload['name']} (ур. {payload['level']}) — "
        f"{payload['phrase']}"
    )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
