"""Team Pulse — недельный нарратив о здоровье команды (Bucket B killer-feature).

Собирает за неделю: задачи (закрыто/создано/просрочки), эмоции (тренд valence/
stress vs прошлая неделя), прогноз выгорания, настроение питомца, топ-исполнителя —
и складывает в человеческий отчёт для руководителя. Связывает эмоции + задачи +
агентные рекомендации в один артефакт.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application.use_cases.burnout_forecast import forecast_team, team_burnout_summary
from brain_api.infrastructure.db import models as m

ACTIVE_STATUSES = ("todo", "in_progress", "blocked", "review")


@dataclass
class PulseMetrics:
    completed_this_week: int
    completed_prev_week: int
    created_this_week: int
    overdue_now: int
    valence_now: float | None
    valence_prev: float | None
    stress_now: float | None
    stress_prev: float | None
    top_performer: str | None
    top_performer_done: int
    burnout_top: str | None
    burnout_eta: int | None


async def _count_completed(session, team_id, start, end) -> int:
    return int(
        await session.scalar(
            select(func.count()).where(
                m.TaskModel.team_id == team_id,
                m.TaskModel.status == "done",
                m.TaskModel.completed_at.is_not(None),
                m.TaskModel.completed_at >= start,
                m.TaskModel.completed_at < end,
            )
        )
        or 0
    )


async def _avg_emotion(session, team_id, start, end) -> tuple[float | None, float | None]:
    row = (
        await session.execute(
            select(
                func.avg(m.EmotionSignalModel.valence),
                func.avg(m.EmotionSignalModel.stress),
                func.count(),
            ).where(
                m.EmotionSignalModel.team_id == team_id,
                m.EmotionSignalModel.created_at >= start,
                m.EmotionSignalModel.created_at < end,
            )
        )
    ).one()
    valence, stress, count = row
    if not count:
        return None, None
    return round(float(valence), 3), round(float(stress), 3)


async def gather_metrics(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> PulseMetrics:
    now = now or datetime.now(UTC)
    week_start = now - timedelta(days=7)
    prev_start = now - timedelta(days=14)

    completed = await _count_completed(session, team_id, week_start, now)
    completed_prev = await _count_completed(session, team_id, prev_start, week_start)
    created = int(
        await session.scalar(
            select(func.count()).where(
                m.TaskModel.team_id == team_id,
                m.TaskModel.created_at >= week_start,
            )
        )
        or 0
    )
    overdue = int(
        await session.scalar(
            select(func.count()).where(
                m.TaskModel.team_id == team_id,
                m.TaskModel.status.in_(ACTIVE_STATUSES),
                m.TaskModel.deadline.is_not(None),
                m.TaskModel.deadline < now,
            )
        )
        or 0
    )
    valence_now, stress_now = await _avg_emotion(session, team_id, week_start, now)
    valence_prev, stress_prev = await _avg_emotion(session, team_id, prev_start, week_start)

    # Топ-исполнитель недели.
    top_row = (
        await session.execute(
            select(m.UserModel.display_name, func.count())
            .join(m.TaskModel, m.TaskModel.assignee_id == m.UserModel.id)
            .where(
                m.TaskModel.team_id == team_id,
                m.TaskModel.status == "done",
                m.TaskModel.completed_at >= week_start,
            )
            .group_by(m.UserModel.display_name)
            .order_by(func.count().desc())
            .limit(1)
        )
    ).first()
    top_performer = top_row[0] if top_row else None
    top_done = int(top_row[1]) if top_row else 0

    forecasts = await forecast_team(session, team_id, now=now)
    summary = team_burnout_summary(forecasts)
    burnout_top = summary["top"]
    burnout_eta = forecasts[0].eta_days if forecasts and burnout_top else None

    return PulseMetrics(
        completed_this_week=completed,
        completed_prev_week=completed_prev,
        created_this_week=created,
        overdue_now=overdue,
        valence_now=valence_now,
        valence_prev=valence_prev,
        stress_now=stress_now,
        stress_prev=stress_prev,
        top_performer=top_performer,
        top_performer_done=top_done,
        burnout_top=burnout_top,
        burnout_eta=burnout_eta,
    )


def _delta_phrase(now_v: int, prev_v: int) -> str:
    d = now_v - prev_v
    if d > 0:
        return f"+{d} к прошлой неделе"
    if d < 0:
        return f"{d} к прошлой неделе"
    return "как и неделей ранее"


def render_pulse(metrics: PulseMetrics, *, team_name: str = "команда") -> str:
    """Собрать человекочитаемый недельный отчёт (HTML для Telegram)."""
    m_ = metrics
    lines = [f"📊 <b>Team Pulse — {team_name}</b>", ""]
    # Задачи
    lines.append(
        f"✅ Закрыто за неделю: <b>{m_.completed_this_week}</b> "
        f"({_delta_phrase(m_.completed_this_week, m_.completed_prev_week)})."
    )
    lines.append(f"🆕 Создано: {m_.created_this_week} · ⏰ Просрочено сейчас: {m_.overdue_now}.")
    # Настроение
    if m_.valence_now is not None:
        mood_pct = int((m_.valence_now + 1) / 2 * 100)
        trend = ""
        if m_.valence_prev is not None:
            delta = int(((m_.valence_now - m_.valence_prev) / 2) * 100)
            trend = f" ({'+' if delta >= 0 else ''}{delta} п.п.)"
        stress_txt = (
            f", стресс {int(m_.stress_now * 100)}%" if m_.stress_now is not None else ""
        )
        lines.append(f"🫀 Настроение команды: {mood_pct}%{trend}{stress_txt}.")
    else:
        lines.append("🫀 Эмоц. анализ выключен — настроение по сигналам недоступно.")
    # Признание
    if m_.top_performer:
        lines.append(f"🏆 Герой недели: <b>{m_.top_performer}</b> — {m_.top_performer_done} задач.")
    # Риск
    if m_.burnout_top:
        eta = f" (порог ~{m_.burnout_eta} дн)" if m_.burnout_eta else ""
        lines.append(f"🧭 Риск выгорания: <b>{m_.burnout_top}</b>{eta} — стоит разгрузить.")
    # Итоговая рекомендация
    lines.append("")
    lines.append(_overall_recommendation(m_))
    return "\n".join(lines)


def _overall_recommendation(m_: PulseMetrics) -> str:
    if m_.burnout_top:
        return f"💡 Итог: команда тянет, но {m_.burnout_top} на грани — разгрузите на этой неделе."
    if m_.overdue_now >= 3:
        return "💡 Итог: накопились просрочки — стоит пересобрать приоритеты."
    if m_.completed_this_week > m_.completed_prev_week:
        return "💡 Итог: команда ускоряется и в норме. Так держать!"
    return "💡 Итог: стабильная неделя без серьёзных рисков."
