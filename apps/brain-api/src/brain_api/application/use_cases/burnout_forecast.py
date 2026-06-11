"""Предиктивный радар выгорания (Bucket B killer-feature).

Не «кто перегружен сейчас», а «кто выгорит через N дней» — по ТРЕНДУ стресса,
просрочек и нагрузки. Превращает агентный контур из реактивного в проактивный:
агент вмешивается ДО того, как человек сорвётся.

Чистое ядро (`burnout_risk`, `eta_days`) тестируется без БД; резолв сигналов из
`emotion_signals` + `tasks`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.infrastructure.db import models as m

ACTIVE_STATUSES = ("todo", "in_progress", "blocked", "review")
WINDOW_DAYS = 14
RECENT_DAYS = 3
STRESS_THRESHOLD = 0.75  # уровень «горит»

RISK_LEVELS = ("ok", "watch", "high", "critical")


def _slope_per_day(daily: list[float]) -> float:
    """Наклон тренда: средний рост за день (последние RECENT_DAYS vs прежние)."""
    if len(daily) < 2:
        return 0.0
    recent = daily[-RECENT_DAYS:]
    earlier = daily[:-RECENT_DAYS] or daily[:1]
    recent_avg = sum(recent) / len(recent)
    earlier_avg = sum(earlier) / len(earlier)
    span = max(1, len(daily) - len(recent))
    return round((recent_avg - earlier_avg) / span, 4)


def burnout_risk(
    current_stress: float,
    stress_slope: float,
    overdue_ratio: float,
    overload_factor: float,
) -> float:
    """Композитный риск выгорания 0..1.

    Сейчас (стресс/просрочки/перегруз) + траектория (растущий стресс усиливает).
    """
    base = (
        0.70 * _clamp(current_stress)
        + 0.15 * _clamp(overdue_ratio)
        + 0.15 * _clamp(overload_factor)
    )
    # Растущий тренд добавляет до +0.30; падающий — снижает.
    trend = _clamp(stress_slope * 8.0, -1.0, 1.0)
    risk = base + 0.30 * max(0.0, trend) - 0.10 * max(0.0, -trend)
    return round(_clamp(risk), 3)


def risk_level(risk: float) -> str:
    if risk >= 0.78:
        return "critical"
    if risk >= 0.6:
        return "high"
    if risk >= 0.4:
        return "watch"
    return "ok"


def eta_days(
    current_stress: float, stress_slope: float, threshold: float = STRESS_THRESHOLD
) -> int | None:
    """Через сколько дней стресс достигнет порога при текущем тренде."""
    if stress_slope <= 1e-4 or current_stress >= threshold:
        return 0 if current_stress >= threshold else None
    days = (threshold - current_stress) / stress_slope
    if days <= 0 or days > 60:
        return None
    return int(round(days))


def trend_label(slope: float) -> str:
    if slope > 0.01:
        return "растёт"
    if slope < -0.01:
        return "падает"
    return "стабилен"


@dataclass(frozen=True)
class MemberForecast:
    user_id: UUID
    display_name: str
    telegram_user_id: int | None
    current_stress: float
    stress_slope: float
    trend: str
    overdue_count: int
    active_count: int
    risk: float
    level: str
    eta_days: int | None
    drivers: list[str] = field(default_factory=list)


async def _daily_stress(
    session: AsyncSession, team_id: UUID, user_id: UUID, *, now: datetime
) -> list[float]:
    """Средний стресс по дням за WINDOW_DAYS (нули для дней без сигналов)."""
    since = now - timedelta(days=WINDOW_DAYS)
    rows = (
        await session.execute(
            select(m.EmotionSignalModel.created_at, m.EmotionSignalModel.stress).where(
                m.EmotionSignalModel.team_id == team_id,
                m.EmotionSignalModel.user_id == user_id,
                m.EmotionSignalModel.created_at >= since,
            )
        )
    ).all()
    by_day: dict[date, list[float]] = {}
    for created_at, stress in rows:
        d = (created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)).date()
        by_day.setdefault(d, []).append(float(stress))
    series: list[float] = []
    last = 0.0
    for i in range(WINDOW_DAYS, -1, -1):
        d = (now - timedelta(days=i)).date()
        vals = by_day.get(d)
        if vals:
            last = round(sum(vals) / len(vals), 3)
        # forward-fill: отсутствие сигнала ≠ ноль стресса, тянем последнее значение
        series.append(last)
    return series


async def forecast_team(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> list[MemberForecast]:
    now = now or datetime.now(UTC)
    members = (
        await session.execute(
            select(m.UserModel)
            .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
            .where(m.TeamMemberModel.team_id == team_id)
        )
    ).scalars().all()
    forecasts: list[MemberForecast] = []
    for user in members:
        active = (
            await session.execute(
                select(m.TaskModel).where(
                    m.TaskModel.team_id == team_id,
                    m.TaskModel.assignee_id == user.id,
                    m.TaskModel.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalars().all()
        active_count = len(active)
        overdue = sum(
            1 for t in active if t.deadline is not None and _as_utc(t.deadline) < now
        )
        overdue_ratio = overdue / active_count if active_count else 0.0
        overload_factor = min(1.0, active_count / 6.0)

        daily = await _daily_stress(session, team_id, user.id, now=now)
        non_zero = [v for v in daily if v > 0]
        # Текущий стресс = пик из последних дней (последнее значение vs 3-дн среднее),
        # чтобы кратковременный спад не «замаскировал» высокий уровень.
        recent_avg = sum(daily[-RECENT_DAYS:]) / RECENT_DAYS if daily else 0.0
        current_stress = round(max(daily[-1] if daily else 0.0, recent_avg), 3)
        slope = _slope_per_day(daily)
        risk = burnout_risk(current_stress, slope, overdue_ratio, overload_factor)
        level = risk_level(risk)
        eta = eta_days(current_stress, slope)

        drivers: list[str] = []
        if slope > 0.01 and non_zero:
            drivers.append("стресс растёт")
        if overdue >= 2:
            drivers.append(f"{overdue} просрочки")
        if active_count >= 5:
            drivers.append(f"{active_count} задач в работе")
        if current_stress >= STRESS_THRESHOLD:
            drivers.append("стресс уже высокий")

        forecasts.append(
            MemberForecast(
                user_id=user.id,
                display_name=user.display_name,
                telegram_user_id=user.telegram_user_id,
                current_stress=current_stress,
                stress_slope=slope,
                trend=trend_label(slope),
                overdue_count=overdue,
                active_count=active_count,
                risk=risk,
                level=level,
                eta_days=eta,
                drivers=drivers,
            )
        )
    forecasts.sort(key=lambda f: f.risk, reverse=True)
    return forecasts


def team_burnout_summary(forecasts: list[MemberForecast]) -> dict:
    at_risk = [f for f in forecasts if f.level in ("high", "critical")]
    return {
        "at_risk_count": len(at_risk),
        "max_risk": max((f.risk for f in forecasts), default=0.0),
        "top": at_risk[0].display_name if at_risk else None,
    }


def render_forecast_text(forecasts: list[MemberForecast]) -> str:
    """Рендер прогноза для чата (HTML)."""
    flagged = [f for f in forecasts if f.level in ("watch", "high", "critical")]
    if not flagged:
        return "🟢 Радар выгорания: команда в норме, растущих рисков не вижу."
    emoji = {"watch": "🟡", "high": "🟠", "critical": "🔴"}
    lines = ["🧭 <b>Радар выгорания</b> (прогноз по тренду)"]
    for f in flagged[:6]:
        eta = (
            f" → порог через ~{f.eta_days} дн" if f.eta_days else ""
        )
        drivers = f"; {', '.join(f.drivers)}" if f.drivers else ""
        lines.append(
            f"{emoji.get(f.level, '🟡')} <b>{f.display_name}</b>: риск "
            f"{int(f.risk*100)}%, стресс {f.trend}{eta}{drivers}"
        )
    return "\n".join(lines)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
