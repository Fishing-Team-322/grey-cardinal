"""Manager Copilot (Bucket B killer-feature).

Каждое утро (или по запросу) формирует руководителю короткий бриф: ТОП-3
действия на сегодня — разгрузить выгорающего, закрыть риск по дедлайну,
разблокировать, похвалить героя. Автономный второй пилот для PM.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application.use_cases.burnout_forecast import forecast_team
from brain_api.infrastructure.db import models as m

ACTIVE_STATUSES = ("todo", "in_progress", "blocked", "review")
DUE_SOON_HOURS = 48


@dataclass(frozen=True)
class CopilotAction:
    priority: int           # меньше = важнее
    icon: str
    text: str
    kind: str               # unload | deadline | unblock | recognize


async def build_actions(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> list[CopilotAction]:
    now = now or datetime.now(UTC)
    actions: list[CopilotAction] = []

    # 1) Разгрузить выгорающего.
    forecasts = await forecast_team(session, team_id, now=now)
    for f in forecasts:
        if f.level in ("high", "critical"):
            eta = f" (порог ~{f.eta_days} дн)" if f.eta_days else ""
            actions.append(CopilotAction(
                priority=1 if f.level == "critical" else 2,
                icon="🧭",
                text=f"Разгрузи {f.display_name} — риск выгорания {int(f.risk*100)}%{eta}.",
                kind="unload",
            ))
            break

    # 2) Дедлайны под риском (просрочено или горит ≤48ч).
    soon = now + timedelta(hours=DUE_SOON_HOURS)
    risky = (
        await session.execute(
            select(m.TaskModel, m.UserModel.display_name)
            .outerjoin(m.UserModel, m.UserModel.id == m.TaskModel.assignee_id)
            .where(
                m.TaskModel.team_id == team_id,
                m.TaskModel.status.in_(ACTIVE_STATUSES),
                m.TaskModel.deadline.is_not(None),
                m.TaskModel.deadline < soon,
            )
            .order_by(m.TaskModel.deadline.asc())
            .limit(3)
        )
    ).all()
    overdue = [(t, name) for t, name in risky if t.deadline and _as_utc(t.deadline) < now]
    if overdue:
        t, name = overdue[0]
        who = f" ({name})" if name else ""
        actions.append(CopilotAction(
            priority=2, icon="⏰",
            text=f"Просрочено: {t.public_id} «{t.title}»{who} — пересобери срок.",
            kind="deadline",
        ))
    elif risky:
        t, name = risky[0]
        who = f" ({name})" if name else ""
        actions.append(CopilotAction(
            priority=4, icon="⏳",
            text=f"Скоро дедлайн: {t.public_id} «{t.title}»{who}.",
            kind="deadline",
        ))

    # 3) Разблокировать.
    blocked = (
        await session.execute(
            select(m.TaskModel, m.UserModel.display_name)
            .outerjoin(m.UserModel, m.UserModel.id == m.TaskModel.assignee_id)
            .where(m.TaskModel.team_id == team_id, m.TaskModel.status == "blocked")
            .limit(1)
        )
    ).first()
    if blocked:
        t, name = blocked
        who = f"{name}: " if name else ""
        actions.append(CopilotAction(
            priority=3, icon="🔓",
            text=f"Разблокируй {who}{t.public_id} «{t.title}».",
            kind="unblock",
        ))

    # 4) Похвалить героя недели.
    week_ago = now - timedelta(days=7)
    top = (
        await session.execute(
            select(m.UserModel.display_name, func.count())
            .join(m.TaskModel, m.TaskModel.assignee_id == m.UserModel.id)
            .where(
                m.TaskModel.team_id == team_id,
                m.TaskModel.status == "done",
                m.TaskModel.completed_at >= week_ago,
            )
            .group_by(m.UserModel.display_name)
            .order_by(func.count().desc())
            .limit(1)
        )
    ).first()
    if top and int(top[1]) >= 2:
        actions.append(CopilotAction(
            priority=5, icon="🏆",
            text=f"Похвали {top[0]} — закрыл(а) {int(top[1])} задач за неделю.",
            kind="recognize",
        ))

    actions.sort(key=lambda a: a.priority)
    return actions[:3]


def render_copilot(actions: list[CopilotAction], *, team_name: str = "команда") -> str:
    if not actions:
        return (
            f"☕️ <b>Копилот — {team_name}</b>\n\n"
            "Сегодня горящего нет: рисков выгорания, просрочек и блоков не вижу. "
            "Хороший день, чтобы двигать стратегию."
        )
    lines = [f"☕️ <b>Копилот — {team_name}</b>", "Три вещи на сегодня:", ""]
    for i, a in enumerate(actions, start=1):
        lines.append(f"{i}. {a.icon} {a.text}")
    return "\n".join(lines)


async def copilot_for_manager(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> str:
    team = await session.get(m.TeamModel, team_id)
    actions = await build_actions(session, team_id, now=now)
    return render_copilot(actions, team_name=team.name if team else "команда")


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
