"""Manager-only employee performance reports."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application.use_cases.team_gamification import level_for_points
from brain_api.infrastructure.db import models as m

ACTIVE_STATUSES = {"todo", "in_progress", "blocked", "review", "confirmed", "proposed"}


async def member_report_payload(
    session: AsyncSession,
    *,
    team_id: UUID,
    user_id: UUID,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    now = now or datetime.now(UTC)
    membership = await session.scalar(
        select(m.TeamMemberModel).where(
            m.TeamMemberModel.team_id == team_id,
            m.TeamMemberModel.user_id == user_id,
        )
    )
    user = await session.get(m.UserModel, user_id)
    team = await session.get(m.TeamModel, team_id)
    if membership is None or user is None or team is None:
        return None

    tasks = (
        await session.execute(
            select(m.TaskModel)
            .where(m.TaskModel.team_id == team_id, m.TaskModel.assignee_id == user_id)
            .order_by(m.TaskModel.updated_at.desc())
        )
    ).scalars().all()
    task_ids = [task.id for task in tasks]
    meeting_ids = list(
        (
            await session.execute(
                select(m.MeetingModel.id).where(m.MeetingModel.team_id == team_id)
            )
        ).scalars()
    )
    board_task_ids = set()
    if task_ids:
        board_task_ids = set(
            (
                await session.execute(
                    select(m.BoardCardModel.task_id).where(m.BoardCardModel.task_id.in_(task_ids))
                )
            ).scalars()
        )
    authors = await _source_authors(session, tasks)

    done = [task for task in tasks if task.status == "done"]
    active = [task for task in tasks if task.status in ACTIVE_STATUSES]
    overdue = [
        task
        for task in active
        if task.deadline is not None and _as_utc(task.deadline) < now
    ]
    completed_with_deadline = [task for task in done if task.deadline and task.completed_at]
    on_time = [
        task
        for task in completed_with_deadline
        if _as_utc(task.completed_at) <= _as_utc(task.deadline)
    ]
    durations = [
        max(0.0, (_as_utc(task.completed_at) - _as_utc(task.created_at)).total_seconds() / 3600)
        for task in done
        if task.completed_at is not None
    ]
    status_counts = Counter(task.status for task in tasks)
    source_counts = Counter(task.source or "unknown" for task in tasks)

    total = len(tasks)
    completion_rate = _percent(len(done), total)
    on_time_rate = (
        _percent(len(on_time), len(completed_with_deadline))
        if completed_with_deadline
        else None
    )
    status_updates_30d = int(
        await session.scalar(
            select(func.count())
            .select_from(m.UserXpEventModel)
            .where(
                m.UserXpEventModel.user_id == user_id,
                m.UserXpEventModel.kind == "status_updated",
                or_(
                    m.UserXpEventModel.workspace_id == team_id,
                    m.UserXpEventModel.task_id.in_(task_ids),
                ),
                m.UserXpEventModel.created_at >= now - timedelta(days=30),
            )
        )
        or 0
    )
    activity_score = min(100, status_updates_30d * 10)
    deadline_component = on_time_rate if on_time_rate is not None else completion_rate
    performance_index = round(
        completion_rate * 0.5 + deadline_component * 0.35 + activity_score * 0.15
    )
    points = int(
        await session.scalar(
            select(func.coalesce(func.sum(m.UserXpEventModel.points), 0)).where(
                m.UserXpEventModel.user_id == user_id,
                or_(
                    m.UserXpEventModel.workspace_id == team_id,
                    m.UserXpEventModel.task_id.in_(task_ids),
                    m.UserXpEventModel.meeting_id.in_(meeting_ids),
                ),
            )
        )
        or 0
    )

    return {
        "team": {"id": str(team.id), "name": team.name},
        "member": {
            "id": str(user.id),
            "display_name": user.display_name,
            "telegram_username": user.telegram_username,
            "role": membership.role,
        },
        "metrics": {
            "assigned_total": total,
            "open_tasks": len(active),
            "completed_total": len(done),
            "completed_7d": _completed_since(done, now - timedelta(days=7)),
            "completed_30d": _completed_since(done, now - timedelta(days=30)),
            "overdue_open": len(overdue),
            "blocked_open": status_counts["blocked"],
            "completion_rate": completion_rate,
            "on_time_rate": on_time_rate,
            "avg_completion_hours": round(sum(durations) / len(durations), 1)
            if durations
            else None,
            "board_synced_tasks": len(board_task_ids),
            "status_updates_30d": status_updates_30d,
            "points": points,
            "level": level_for_points(points),
            "performance_index": performance_index,
            "performance_formula": (
                "50% закрываемость + 35% выполнение в срок + 15% обновления статусов"
            ),
        },
        "status_breakdown": dict(status_counts),
        "source_breakdown": dict(source_counts),
        "active_tasks": [
            _task_payload(task, authors.get(task.source_message_id), task.id in board_task_ids)
            for task in active[:8]
        ],
        "recent_completed": [
            _task_payload(task, authors.get(task.source_message_id), task.id in board_task_ids)
            for task in sorted(
                done,
                key=lambda item: _as_utc(item.completed_at or item.updated_at),
                reverse=True,
            )[:8]
        ],
    }


async def manager_report_menu(
    session: AsyncSession, telegram_user_id: int
) -> tuple[str, dict[str, Any] | None]:
    manager = await session.scalar(
        select(m.UserModel).where(m.UserModel.telegram_user_id == telegram_user_id)
    )
    if manager is None:
        return "Сначала привяжите Telegram к аккаунту Grey Cardinal.", None
    manager_teams = select(m.TeamMemberModel.team_id).where(
        m.TeamMemberModel.user_id == manager.id,
        m.TeamMemberModel.role == "manager",
    )
    rows = (
        await session.execute(
            select(m.TeamMemberModel, m.UserModel, m.TeamModel)
            .join(m.UserModel, m.UserModel.id == m.TeamMemberModel.user_id)
            .join(m.TeamModel, m.TeamModel.id == m.TeamMemberModel.team_id)
            .where(
                m.TeamMemberModel.team_id.in_(manager_teams),
                m.TeamMemberModel.user_id != manager.id,
            )
            .order_by(m.TeamModel.name, m.UserModel.display_name)
        )
    ).all()
    if not rows:
        return "В ваших командах пока нет сотрудников для отчёта.", None
    buttons = [
        [
            {
                "text": f"{team.name}: {user.display_name}"[:60],
                "callback_data": f"report:member:{membership.id}",
            }
        ]
        for membership, user, team in rows[:30]
    ]
    return "📈 Выберите сотрудника для персонального отчёта:", {"inline_keyboard": buttons}


async def manager_report_from_membership(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    membership_id: UUID,
) -> dict[str, Any] | None:
    manager = await session.scalar(
        select(m.UserModel).where(m.UserModel.telegram_user_id == telegram_user_id)
    )
    membership = await session.get(m.TeamMemberModel, membership_id)
    if manager is None or membership is None:
        return None
    allowed = await session.scalar(
        select(m.TeamMemberModel.id).where(
            m.TeamMemberModel.team_id == membership.team_id,
            m.TeamMemberModel.user_id == manager.id,
            m.TeamMemberModel.role == "manager",
        )
    )
    if allowed is None:
        return None
    return await member_report_payload(
        session,
        team_id=membership.team_id,
        user_id=membership.user_id,
    )


def render_member_report(report: dict[str, Any]) -> str:
    member = report["member"]
    metrics = report["metrics"]
    on_time = (
        f"{metrics['on_time_rate']}%"
        if metrics["on_time_rate"] is not None
        else "нет задач с дедлайном"
    )
    avg = (
        f"{metrics['avg_completion_hours']} ч"
        if metrics["avg_completion_hours"] is not None
        else "пока нет данных"
    )
    sources = ", ".join(
        f"{name}: {count}" for name, count in report["source_breakdown"].items()
    ) or "нет"
    lines = [
        f"📈 Отчёт: {member['display_name']}",
        f"Команда: {report['team']['name']}",
        "",
        f"Индекс выполнения: {metrics['performance_index']}/100",
        f"XP: {metrics['points']}, уровень {metrics['level']}",
        f"Назначено: {metrics['assigned_total']}",
        f"Закрыто: {metrics['completed_total']} "
        f"(за 7 дней: {metrics['completed_7d']}, за 30 дней: {metrics['completed_30d']})",
        f"Сейчас открыто: {metrics['open_tasks']}; просрочено: {metrics['overdue_open']}; "
        f"заблокировано: {metrics['blocked_open']}",
        f"Среднее время закрытия: {avg}",
        f"Выполнено в срок: {on_time}",
        f"Синхронизировано с доской: {metrics['board_synced_tasks']}",
        f"Источники задач: {sources}",
        "",
        f"Формула индекса: {metrics['performance_formula']}.",
    ]
    if report["active_tasks"]:
        lines.extend(["", "Текущие задачи:"])
        lines.extend(_render_task_line(task) for task in report["active_tasks"][:5])
    if report["recent_completed"]:
        lines.extend(["", "Последние закрытые:"])
        lines.extend(_render_task_line(task) for task in report["recent_completed"][:5])
    return "\n".join(lines)[:3900]


async def _source_authors(
    session: AsyncSession, tasks: list[m.TaskModel]
) -> dict[UUID | None, str | None]:
    message_ids = [task.source_message_id for task in tasks if task.source_message_id is not None]
    if not message_ids:
        return {}
    rows = await session.execute(
        select(m.ChatMessageModel.id, m.UserModel.display_name)
        .outerjoin(m.UserModel, m.UserModel.id == m.ChatMessageModel.sender_id)
        .where(m.ChatMessageModel.id.in_(message_ids))
    )
    return dict(rows.all())


def _task_payload(
    task: m.TaskModel, source_author: str | None, board_synced: bool
) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "public_id": task.public_id,
        "title": task.title,
        "status": task.status,
        "source": task.source,
        "source_author": source_author,
        "deadline": task.deadline,
        "completed_at": task.completed_at,
        "board_synced": board_synced,
    }


def _render_task_line(task: dict[str, Any]) -> str:
    author = f", от {task['source_author']}" if task["source_author"] else ""
    board = ", доска ✓" if task["board_synced"] else ""
    return (
        f"• {task['public_id']} {task['title']} — "
        f"{task['status']} ({task['source']}{author}{board})"
    )


def _completed_since(tasks: list[m.TaskModel], since: datetime) -> int:
    return sum(
        1
        for task in tasks
        if task.completed_at is not None and _as_utc(task.completed_at) >= since
    )


def _percent(value: int, total: int) -> int:
    return round(value / total * 100) if total else 0


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
