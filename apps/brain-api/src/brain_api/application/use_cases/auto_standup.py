"""Стендап без стендапа (Bucket B killer-feature).

AI синтезирует утренний стендап из данных, а не из митинга: кто над чем
работает, кто заблокирован, кто вчера что закрыл и кому нужна помощь (по риску
выгорания). Заменяет ручные дейли.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application.use_cases.burnout_forecast import forecast_team
from brain_api.infrastructure.db import models as m

DONE_LOOKBACK_HOURS = 36


@dataclass
class MemberStandup:
    display_name: str
    doing: list[str] = field(default_factory=list)       # GC-N титулы (in_progress)
    blocked: list[str] = field(default_factory=list)     # заблокированные
    done_recently: list[str] = field(default_factory=list)
    needs_help: bool = False
    help_reason: str = ""


@dataclass
class TeamStandup:
    members: list[MemberStandup]
    total_blocked: int
    needs_help: list[str]


def _short(task: m.TaskModel) -> str:
    return f"{task.public_id} {task.title}"[:60]


async def build_standup(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> TeamStandup:
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=DONE_LOOKBACK_HOURS)

    members = (
        await session.execute(
            select(m.UserModel)
            .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
            .where(m.TeamMemberModel.team_id == team_id)
        )
    ).scalars().all()

    forecasts = {f.user_id: f for f in await forecast_team(session, team_id, now=now)}

    result: list[MemberStandup] = []
    total_blocked = 0
    needs_help_names: list[str] = []
    for user in members:
        tasks = (
            await session.execute(
                select(m.TaskModel).where(
                    m.TaskModel.team_id == team_id,
                    m.TaskModel.assignee_id == user.id,
                )
            )
        ).scalars().all()
        doing = [_short(t) for t in tasks if t.status == "in_progress"]
        blocked = [_short(t) for t in tasks if t.status == "blocked"]
        done_recent = [
            _short(t)
            for t in tasks
            if t.status == "done" and t.completed_at is not None
            and _as_utc(t.completed_at) >= since
        ]
        total_blocked += len(blocked)

        fc = forecasts.get(user.id)
        needs_help = bool(blocked) or (fc is not None and fc.level in ("high", "critical"))
        reason = ""
        if blocked:
            reason = "заблокирован(а)"
        elif fc is not None and fc.level in ("high", "critical"):
            reason = f"риск выгорания {int(fc.risk * 100)}%"
        if needs_help:
            needs_help_names.append(user.display_name)

        # Не показываем совсем пустых участников (без активности).
        if doing or blocked or done_recent or needs_help:
            result.append(
                MemberStandup(
                    display_name=user.display_name,
                    doing=doing, blocked=blocked, done_recently=done_recent,
                    needs_help=needs_help, help_reason=reason,
                )
            )
    return TeamStandup(
        members=result, total_blocked=total_blocked, needs_help=needs_help_names
    )


def render_standup(standup: TeamStandup, *, team_name: str = "команда") -> str:
    """Рендер утреннего стендапа для чата (HTML)."""
    if not standup.members:
        return "🌅 Доброе утро! Активных задач пока нет — чистый старт дня."
    lines = [f"🌅 <b>Утренний стендап — {team_name}</b>", ""]
    for ms in standup.members:
        head = f"<b>{ms.display_name}</b>"
        if ms.needs_help:
            head += " 🆘"
        lines.append(head)
        if ms.doing:
            lines.append("  🔄 " + "; ".join(ms.doing))
        if ms.blocked:
            lines.append("  ⛔ " + "; ".join(ms.blocked))
        if ms.done_recently:
            lines.append("  ✅ " + "; ".join(ms.done_recently))
        if ms.needs_help and ms.help_reason:
            lines.append(f"  💬 нужна помощь: {ms.help_reason}")
    if standup.needs_help:
        lines.append("")
        lines.append(f"🤝 Внимание: помощь нужна — {', '.join(standup.needs_help)}.")
    return "\n".join(lines)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
