"""Account XP, achievements, and team leaderboard helpers."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.infrastructure.db import models as m

LEVEL_XP = 100
TASK_COMPLETED_XP = 20
MEETING_SUMMARY_XP = 5

ACHIEVEMENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "first_finish",
        "title": "Первый финиш",
        "description": "Закрыть первую задачу",
        "kind": "task_completed",
        "target": 1,
    },
    {
        "id": "reliable_five",
        "title": "Надёжный исполнитель",
        "description": "Закрыть 5 задач",
        "kind": "task_completed",
        "target": 5,
    },
    {
        "id": "closer",
        "title": "Клоузер",
        "description": "Закрыть 10 задач",
        "kind": "task_completed",
        "target": 10,
    },
    {
        "id": "status_pilot",
        "title": "Всегда на связи",
        "description": "Обновить статус задач 10 раз",
        "kind": "status_updated",
        "target": 10,
    },
    {
        "id": "voice_pioneer",
        "title": "Голос в дело",
        "description": "Создать задачу из речи",
        "kind": "task_created_from_speech",
        "target": 1,
    },
    {
        "id": "meeting_regular",
        "title": "Командный игрок",
        "description": "Присоединиться к 5 созвонам",
        "kind": "meeting_joined",
        "target": 5,
    },
    {
        "id": "summary_keeper",
        "title": "Хранитель итогов",
        "description": "Получить 3 саммари созвонов",
        "kind": "meeting_summary_ready",
        "target": 3,
    },
    {
        "id": "risk_tamer",
        "title": "Укротитель рисков",
        "description": "Закрыть первый риск",
        "kind": "risk_resolved",
        "target": 1,
    },
)


async def grant_team_xp(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    team_id: UUID,
    kind: str,
    points: int,
    reason: str,
    idempotency_key: str,
    task_id: UUID | None = None,
    meeting_id: UUID | None = None,
) -> bool:
    """Grant team-scoped XP once without committing the surrounding transaction."""
    if user_id is None:
        return False
    existing = await session.scalar(
        select(m.UserXpEventModel).where(
            m.UserXpEventModel.user_id == user_id,
            m.UserXpEventModel.kind == kind,
            m.UserXpEventModel.metadata_json["idempotency_key"].as_string()
            == idempotency_key,
        )
    )
    if existing is not None:
        return False

    session.add(
        m.UserXpEventModel(
            id=uuid4(),
            user_id=user_id,
            workspace_id=team_id,
            task_id=task_id,
            meeting_id=meeting_id,
            kind=kind,
            points=points,
            reason=reason,
            metadata_json={"idempotency_key": idempotency_key, "team_id": str(team_id)},
        )
    )
    total = await session.scalar(
        select(m.UserXpTotalModel).where(
            m.UserXpTotalModel.user_id == user_id,
            m.UserXpTotalModel.workspace_id == team_id,
        )
    )
    if total is None:
        total = m.UserXpTotalModel(
            id=uuid4(),
            user_id=user_id,
            workspace_id=team_id,
            points_total=0,
            level=1,
        )
        session.add(total)
    total.points_total += points
    total.level = level_for_points(total.points_total)
    await session.flush()
    return True


def level_for_points(points: int) -> int:
    return max(1, points // LEVEL_XP + 1)


async def gamification_profile_payload(session: AsyncSession, user_id: UUID) -> dict[str, Any]:
    total = int(
        await session.scalar(
            select(func.coalesce(func.sum(m.UserXpEventModel.points), 0)).where(
                m.UserXpEventModel.user_id == user_id
            )
        )
        or 0
    )
    kind_rows = await session.execute(
        select(m.UserXpEventModel.kind, func.count())
        .where(m.UserXpEventModel.user_id == user_id)
        .group_by(m.UserXpEventModel.kind)
    )
    counts = {kind: int(count) for kind, count in kind_rows.all()}
    recent_rows = (
        await session.execute(
            select(m.UserXpEventModel)
            .where(m.UserXpEventModel.user_id == user_id)
            .order_by(m.UserXpEventModel.created_at.desc())
            .limit(8)
        )
    ).scalars()
    level = level_for_points(total)
    return {
        "points_total": total,
        "level": level,
        "level_xp": total % LEVEL_XP,
        "next_level_xp": LEVEL_XP,
        "achievements": _achievement_payload(counts),
        "recent_events": [
            {
                "id": str(row.id),
                "kind": row.kind,
                "points": row.points,
                "reason": row.reason,
                "created_at": row.created_at,
            }
            for row in recent_rows
        ],
    }


async def team_leaderboard_payload(session: AsyncSession, team_id: UUID) -> dict[str, Any]:
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        return {"team_id": str(team_id), "team_name": "", "items": []}

    task_ids = select(m.TaskModel.id).where(m.TaskModel.team_id == team_id)
    meeting_ids = select(m.MeetingModel.id).where(m.MeetingModel.team_id == team_id)
    members = (
        await session.execute(
            select(m.UserModel, m.TeamMemberModel.role)
            .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
            .where(m.TeamMemberModel.team_id == team_id)
        )
    ).all()
    items: list[dict[str, Any]] = []
    for user, role in members:
        event_scope = or_(
            m.UserXpEventModel.workspace_id == team_id,
            m.UserXpEventModel.task_id.in_(task_ids),
            m.UserXpEventModel.meeting_id.in_(meeting_ids),
        )
        points = int(
            await session.scalar(
                select(func.coalesce(func.sum(m.UserXpEventModel.points), 0)).where(
                    m.UserXpEventModel.user_id == user.id,
                    event_scope,
                )
            )
            or 0
        )
        completed = int(
            await session.scalar(
                select(func.count(func.distinct(m.UserXpEventModel.task_id))).where(
                    m.UserXpEventModel.user_id == user.id,
                    m.UserXpEventModel.kind == "task_completed",
                    m.UserXpEventModel.task_id.in_(task_ids),
                )
            )
            or 0
        )
        items.append(
            {
                "user_id": str(user.id),
                "display_name": user.display_name,
                "telegram_username": user.telegram_username,
                "role": role,
                "points": points,
                "level": level_for_points(points),
                "completed_tasks": completed,
            }
        )
    items.sort(key=lambda item: (-item["points"], -item["completed_tasks"], item["display_name"]))
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
    return {"team_id": str(team.id), "team_name": team.name, "items": items}


async def team_leaderboard_text_for_chat(session: AsyncSession, chat_id: int) -> str:
    team = await session.scalar(select(m.TeamModel).where(m.TeamModel.tg_chat_id == chat_id))
    if team is None:
        return "Лидерборд недоступен: сначала привяжите Telegram-группу к команде."
    payload = await team_leaderboard_payload(session, team.id)
    if not payload["items"]:
        return f"Лидерборд команды {team.name} пока пуст."
    lines = [f"🏆 Лидерборд команды {team.name}", ""]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for item in payload["items"][:10]:
        prefix = medals.get(item["rank"], f"{item['rank']}.")
        lines.append(
            f"{prefix} {item['display_name']} — {item['points']} XP, "
            f"уровень {item['level']}, задач закрыто: {item['completed_tasks']}"
        )
    return "\n".join(lines)


def _achievement_payload(counts: dict[str, int]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for achievement in ACHIEVEMENTS:
        progress = counts.get(str(achievement["kind"]), 0)
        target = int(achievement["target"])
        result.append(
            {
                "id": achievement["id"],
                "title": achievement["title"],
                "description": achievement["description"],
                "progress": min(progress, target),
                "target": target,
                "unlocked": progress >= target,
            }
        )
    return result
