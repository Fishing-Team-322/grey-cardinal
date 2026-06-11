"""Scoring engine командного питомца.

Считает 6 нормализованных метрик (0..100) и итоговую силу команды по формуле:

    Team Power = 35% productivity + 25% harmony + 20% communication
               + 10% wellbeing + 10% stability

`tension` считается отдельно (0 — хорошо, 100 — плохо). Чистые формулы вынесены
в :func:`compute_scores`, чтобы их легко тестировать; сбор данных из БД — в
:func:`gather_inputs`. Privacy влияет на то, учитывать ли chat/task сигналы.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import pstdev
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application.use_cases.agentic_wellbeing import _member_loads
from brain_api.infrastructure.db import models as m

ACTIVE_STATUSES = ("todo", "in_progress", "blocked", "review")
PROD_WINDOW_DAYS = 7
EMOTION_WINDOW_DAYS = 7

# Веса итоговой силы команды.
W_PRODUCTIVITY = 0.35
W_HARMONY = 0.25
W_COMMUNICATION = 0.20
W_WELLBEING = 0.10
W_STABILITY = 0.10


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class ScoringInputs:
    """Нормализованные входы для расчёта (всё, что нужно формулам)."""

    active_count: int = 0
    overdue_count: int = 0
    blocked_count: int = 0
    done_recent: int = 0          # закрыто за последние 7 дней
    done_prev: int = 0            # закрыто за предыдущие 7 дней
    done_no_overdue: int = 0      # всего закрыто без просрочки (для анлоков)
    member_count: int = 0
    at_risk_count: int = 0
    load_values: tuple[int, ...] = ()  # active per member (равномерность)
    emotion_valence: float | None = None  # -1..1
    emotion_stress: float | None = None   # 0..1
    emotion_count: int = 0

    @property
    def overdue_pressure(self) -> float:
        return self.overdue_count / self.active_count if self.active_count else 0.0

    @property
    def blocked_ratio(self) -> float:
        return self.blocked_count / self.active_count if self.active_count else 0.0

    @property
    def activity(self) -> float:
        return min(1.0, self.done_recent / max(3, self.active_count or 3))

    @property
    def evenness(self) -> float:
        """1 — нагрузка ровная, 0 — очень неравномерная."""
        if len(self.load_values) < 2:
            return 0.7
        mean = sum(self.load_values) / len(self.load_values)
        if mean <= 0:
            return 1.0
        return _clamp(1.0 - pstdev(self.load_values) / (mean + 1e-9), 0.0, 1.0)


@dataclass(frozen=True)
class Scores:
    productivity: float
    harmony: float
    communication: float
    wellbeing: float
    stability: float
    tension: float
    power: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "productivity": self.productivity,
            "harmony": self.harmony,
            "communication": self.communication,
            "wellbeing": self.wellbeing,
            "stability": self.stability,
            "tension": self.tension,
            "power": self.power,
        }


def compute_scores(inp: ScoringInputs) -> Scores:
    """Чистый расчёт всех метрик из нормализованных входов."""
    op_ = inp.overdue_pressure
    activity = inp.activity

    productivity = _clamp(100 * (0.55 + 0.45 * activity - 0.60 * op_))
    if inp.done_recent > inp.done_prev:
        productivity = _clamp(productivity + 4)  # положительная динамика

    if inp.member_count < 2 and inp.active_count < 2:
        harmony = 68.0  # данных мало — нейтрально-хорошо
    else:
        harmony = _clamp(100 * (0.40 + 0.40 * inp.evenness + 0.20 * activity)
                         - 30 * inp.blocked_ratio)

    if inp.emotion_count and inp.emotion_valence is not None:
        valence_norm = (inp.emotion_valence + 1) / 2  # 0..1
        stress = inp.emotion_stress or 0.0
        communication = _clamp(100 * (0.50 + 0.45 * valence_norm - 0.30 * stress))
    else:
        communication = 66.0  # нет chat-сигналов / анализ выключен — нейтрально

    at_risk_ratio = inp.at_risk_count / inp.member_count if inp.member_count else 0.0
    stress = inp.emotion_stress or 0.0
    wellbeing = _clamp(88 - 40 * at_risk_ratio - 30 * stress - 20 * op_)

    stability = _clamp(100 * (0.60 + 0.40 * activity - 0.50 * op_ - 0.30 * inp.blocked_ratio))

    neg = _clamp(-(inp.emotion_valence or 0.0), 0.0, 1.0)
    if inp.emotion_count:
        tension = _clamp(100 * (0.40 * neg + 0.60 * stress) + 20 * op_)
    else:
        tension = _clamp(100 * (0.50 * op_))

    weighted = (
        W_PRODUCTIVITY * productivity
        + W_HARMONY * harmony
        + W_COMMUNICATION * communication
        + W_WELLBEING * wellbeing
        + W_STABILITY * stability
    )
    power = round(weighted * 100)
    return Scores(
        productivity=round(productivity, 1),
        harmony=round(harmony, 1),
        communication=round(communication, 1),
        wellbeing=round(wellbeing, 1),
        stability=round(stability, 1),
        tension=round(tension, 1),
        power=power,
    )


async def gather_inputs(
    session: AsyncSession,
    team_id: UUID,
    *,
    now: datetime,
    analyze_tasks: bool = True,
    analyze_chat: bool = True,
) -> ScoringInputs:
    """Собрать входы из БД с учётом privacy-флагов."""
    active = (
        (
            await session.execute(
                select(m.TaskModel).where(
                    m.TaskModel.team_id == team_id,
                    m.TaskModel.status.in_(ACTIVE_STATUSES),
                )
            )
        )
        .scalars()
        .all()
    )
    active_count = len(active) if analyze_tasks else 0
    overdue = (
        sum(1 for t in active if t.deadline is not None and _as_utc(t.deadline) < now)
        if analyze_tasks
        else 0
    )
    blocked = sum(1 for t in active if t.status == "blocked") if analyze_tasks else 0

    since = now - timedelta(days=PROD_WINDOW_DAYS)
    prev_since = since - timedelta(days=PROD_WINDOW_DAYS)
    done_recent = 0
    done_prev = 0
    done_no_overdue = 0
    if analyze_tasks:
        done_recent = int(
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
        done_prev = int(
            await session.scalar(
                select(func.count()).where(
                    m.TaskModel.team_id == team_id,
                    m.TaskModel.status == "done",
                    m.TaskModel.completed_at.is_not(None),
                    m.TaskModel.completed_at >= prev_since,
                    m.TaskModel.completed_at < since,
                )
            )
            or 0
        )
        done_no_overdue = await _done_no_overdue_count(session, team_id)

    loads = await _member_loads(session, team_id, now=now)
    member_count = len(loads)
    at_risk_count = sum(1 for load in loads if load.at_risk)
    load_values = tuple(load.active_count for load in loads)

    valence: float | None = None
    stress: float | None = None
    emotion_count = 0
    if analyze_chat:
        e_since = now - timedelta(days=EMOTION_WINDOW_DAYS)
        row = (
            await session.execute(
                select(
                    func.avg(m.EmotionSignalModel.valence),
                    func.avg(m.EmotionSignalModel.stress),
                    func.count(),
                ).where(
                    m.EmotionSignalModel.team_id == team_id,
                    m.EmotionSignalModel.created_at >= e_since,
                )
            )
        ).one()
        v_avg, s_avg, count = row
        emotion_count = int(count or 0)
        if emotion_count:
            valence = float(v_avg)
            stress = float(s_avg)

    return ScoringInputs(
        active_count=active_count,
        overdue_count=overdue,
        blocked_count=blocked,
        done_recent=done_recent,
        done_prev=done_prev,
        done_no_overdue=done_no_overdue,
        member_count=member_count,
        at_risk_count=at_risk_count,
        load_values=load_values,
        emotion_valence=valence,
        emotion_stress=stress,
        emotion_count=emotion_count,
    )


async def _done_no_overdue_count(session: AsyncSession, team_id: UUID) -> int:
    """Сколько задач закрыто без просрочки (completed_at <= deadline или без дедлайна)."""
    tasks = (
        (
            await session.execute(
                select(m.TaskModel).where(
                    m.TaskModel.team_id == team_id,
                    m.TaskModel.status == "done",
                    m.TaskModel.completed_at.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    count = 0
    for t in tasks:
        if t.completed_at is None:
            continue
        if t.deadline is None or _as_utc(t.completed_at) <= _as_utc(t.deadline):
            count += 1
    return count


# Метаданные метрик для frontend-карточек.
_METRIC_META = {
    "productivity": ("Продуктивность", False),
    "harmony": ("Слаженность", False),
    "communication": ("Коммуникация", False),
    "wellbeing": ("Wellbeing", False),
    "stability": ("Стабильность", False),
    "tension": ("Напряжение", True),  # invert: меньше — лучше
}


def _status_for(value: float, *, invert: bool) -> str:
    v = 100 - value if invert else value
    if v >= 66:
        return "good"
    if v >= 40:
        return "warn"
    return "bad"


def _synth_sparkline(value: float, delta: float) -> list[int]:
    """7 точек, плавно приходящих к текущему значению (для мини-графика)."""
    start = _clamp(value - delta)
    pts = [round(start + (value - start) * (i / 6)) for i in range(7)]
    pts[-1] = round(value)
    return [int(_clamp(p)) for p in pts]


def build_metric_cards(
    scores: Scores, prev: dict[str, float] | None = None
) -> list[dict[str, Any]]:
    """Собрать список метрик в формате frontend (с трендом и sparkline)."""
    prev = prev or {}
    cards: list[dict[str, Any]] = []
    explanations = _explanations(scores)
    for key, (label, invert) in _METRIC_META.items():
        value = getattr(scores, key)
        delta = round(value - prev.get(key, value), 1)
        status = _status_for(value, invert=invert)
        if key == "tension":
            display = "низкое" if value < 33 else "умеренное" if value < 66 else "высокое"
            trend = "спокойно" if delta <= 0 else "растёт"
        else:
            display = f"{round(value)}%"
            trend = f"+{delta}%" if delta > 0 else (f"{delta}%" if delta < 0 else "стабильно")
        cards.append(
            {
                "key": key,
                "label": label,
                "value": round(value),
                "display": display,
                "trend": trend,
                "status": status,
                "sparkline": _synth_sparkline(value, delta),
                "explanation": explanations.get(key, ""),
            }
        )
    return cards


def _explanations(s: Scores) -> dict[str, str]:
    return {
        "productivity": (
            "Команда стабильно закрывает задачи."
            if s.productivity >= 66
            else "Есть просрочки — стоит пересмотреть приоритеты."
        ),
        "harmony": (
            "Нагрузка распределена ровно, команда слаженна."
            if s.harmony >= 66
            else "Нагрузка распределена неравномерно."
        ),
        "communication": (
            "Коммуникация спокойная и поддерживающая."
            if s.communication >= 66
            else "Тон коммуникации стоит мягко выровнять."
        ),
        "wellbeing": (
            "Баланс нагрузки в норме, риск перегруза низкий."
            if s.wellbeing >= 66
            else "Есть риск перегруза у части участников."
        ),
        "stability": (
            "Процесс ровный, задачи редко перекидываются."
            if s.stability >= 66
            else "Процесс нестабилен — много блокеров или просрочек."
        ),
        "tension": (
            "Напряжение низкое, конфликтных сигналов почти нет."
            if s.tension < 33
            else "Напряжение повышенное — стоит снизить нагрузку."
        ),
    }


async def recompute_scores(
    session: AsyncSession,
    pet: m.TeamPetModel,
    *,
    now: datetime,
    analyze_tasks: bool = True,
    analyze_chat: bool = True,
) -> tuple[Scores, dict[str, float], ScoringInputs]:
    """Пересчитать и записать метрики в питомца. Возвращает (scores, prev, inputs)."""
    prev = {
        "productivity": pet.productivity_score,
        "harmony": pet.harmony_score,
        "communication": pet.communication_score,
        "wellbeing": pet.wellbeing_score,
        "stability": pet.stability_score,
        "tension": pet.tension_score,
        "power": pet.power_score,
    }
    inputs = await gather_inputs(
        session, pet.team_id, now=now, analyze_tasks=analyze_tasks, analyze_chat=analyze_chat
    )
    scores = compute_scores(inputs)
    pet.productivity_score = scores.productivity
    pet.harmony_score = scores.harmony
    pet.communication_score = scores.communication
    pet.wellbeing_score = scores.wellbeing
    pet.stability_score = scores.stability
    pet.tension_score = scores.tension
    pet.power_score = float(scores.power)
    pet.last_scored_at = now
    await session.flush()
    return scores, prev, inputs


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
