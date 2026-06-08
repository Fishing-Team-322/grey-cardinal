"""Напоминание о созвоне за ~5 минут до начала (планировщик, каждую минуту).

Шлёт в личку каждому, кто отметился «Приду» (а если RSVP пуст — всем участникам
команды с привязанным Telegram), что пора запускать даемон Grey Cardinal.
Дедупликация — через флаг `metadata_json.reminded_5min` на самом созвоне.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from brain_api.application.rendering import format_deadline
from brain_api.application.use_cases.team_gamification import (
    MEETING_SUMMARY_XP,
    grant_team_xp,
)
from brain_api.infrastructure.db import models as m

logger = logging.getLogger(__name__)

REMINDER_LEAD_MINUTES = 5


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


async def run_meeting_finalize(
    session_factory,
    gateway,
    now: datetime | None = None,
    llm_provider_factory=None,
) -> int:
    """Завершить созвоны, окно которых прошло, и отправить саммари в чат команды."""
    now = now or datetime.now(UTC)
    finalized = 0
    async with session_factory() as session:
        rows = await session.execute(
            select(m.MeetingModel).where(
                m.MeetingModel.state.in_(("scheduled", "armed", "recording")),
                m.MeetingModel.scheduled_at.is_not(None),
            )
        )
        for meeting in rows.scalars():
            duration = meeting.duration_minutes or 60
            end_at = _as_utc(meeting.scheduled_at) + timedelta(minutes=duration)
            if now < end_at:
                continue
            team = await session.get(m.TeamModel, meeting.team_id)
            window_start = _as_utc(meeting.scheduled_at) - timedelta(minutes=10)
            task_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(m.TaskModel)
                    .where(
                        m.TaskModel.team_id == meeting.team_id,
                        m.TaskModel.created_at >= window_start,
                    )
                )
                or 0
            )
            yes = int(
                await session.scalar(
                    select(func.count())
                    .select_from(m.MeetingRsvpModel)
                    .where(
                        m.MeetingRsvpModel.meeting_id == meeting.id,
                        m.MeetingRsvpModel.status == "yes",
                    )
                )
                or 0
            )
            meeting.state = "finished"
            meeting.status = "finished"
            meeting.stopped_at = now
            meeting.summary = await _meeting_summary(
                session,
                meeting,
                task_count=task_count,
                attendees=yes,
                window_start=window_start,
                end_at=end_at,
                llm_provider_factory=llm_provider_factory,
            )
            if meeting.team_id is not None:
                await grant_team_xp(
                    session,
                    user_id=meeting.created_by or meeting.created_by_user_id,
                    team_id=meeting.team_id,
                    meeting_id=meeting.id,
                    kind="meeting_summary_ready",
                    points=MEETING_SUMMARY_XP,
                    reason=f"Получил саммари созвона {meeting.public_id}",
                    idempotency_key=f"meeting_summary_ready:{meeting.id}",
                )
            if team and team.tg_chat_id:
                when = format_deadline(meeting.scheduled_at, team.timezone)
                text = (
                    f"⏹ Созвон {when} завершён.\n\n"
                    f"{meeting.summary}\n\n"
                    "Карточки и полный итог доступны в Grey Cardinal и на доске YouGile."
                )
                await gateway.send_message(team.tg_chat_id, text)
            finalized += 1
        await session.commit()
    if finalized:
        logger.info("Finalized %d meetings", finalized)
    return finalized


async def _meeting_summary(
    session,
    meeting: m.MeetingModel,
    *,
    task_count: int,
    attendees: int,
    window_start: datetime,
    end_at: datetime,
    llm_provider_factory,
) -> str:
    tasks = (
        await session.execute(
            select(m.TaskModel)
            .where(
                m.TaskModel.team_id == meeting.team_id,
                m.TaskModel.created_at >= window_start,
                m.TaskModel.created_at <= end_at,
            )
            .order_by(m.TaskModel.created_at)
        )
    ).scalars().all()
    transcripts = (
        await session.execute(
            select(m.TranscriptEventModel)
            .where(
                or_(
                    m.TranscriptEventModel.meeting_db_id == meeting.id,
                    m.TranscriptEventModel.meeting_id == meeting.public_id,
                ),
                m.TranscriptEventModel.ts >= window_start,
                m.TranscriptEventModel.ts <= end_at,
                m.TranscriptEventModel.is_final.is_(True),
            )
            .order_by(m.TranscriptEventModel.ts)
            .limit(200)
        )
    ).scalars().all()
    fallback = _fallback_summary(task_count, attendees, tasks)
    if llm_provider_factory is None or meeting.team_id is None:
        return fallback

    transcript_text = "\n".join(
        f"{item.speaker_name or 'Участник'}: {item.text}" for item in transcripts
    )[-12000:]
    task_text = "\n".join(
        f"- {task.public_id}: {task.title}; исполнитель: {task.assignee_text or 'не назначен'}"
        for task in tasks
    )
    prompt = (
        "Составь итог командного созвона на русском языке. Верни строгий JSON с ключами "
        "summary (строка), highlights (массив строк), decisions (массив строк), "
        "next_steps (массив строк), risks (массив строк). Не придумывай факты.\n\n"
        f"Название: {meeting.title or meeting.public_id}\n"
        f"Участников: {attendees}\n"
        f"Созданные задачи:\n{task_text or '- нет'}\n\n"
        f"Транскрипт:\n{transcript_text or 'Транскрипт отсутствует.'}"
    )
    try:
        provider = await llm_provider_factory.for_team(meeting.team_id)
        data = await provider.complete_json(prompt, schema_name="meeting_summary")
        return _format_ai_summary(data, fallback)
    except Exception:
        logger.exception("Meeting AI summary failed for %s", meeting.public_id)
        return fallback


def _fallback_summary(task_count: int, attendees: int, tasks: list[m.TaskModel]) -> str:
    task_lines = [f"• {task.public_id}: {task.title}" for task in tasks[:5]]
    result = [
        "Итог созвона",
        f"Участников: {attendees}. Создано задач: {task_count}.",
    ]
    if task_lines:
        result.extend(["", "Следующие шаги:", *task_lines])
    return "\n".join(result)[:3500]


def _format_ai_summary(data: dict[str, Any], fallback: str) -> str:
    summary = str(data.get("summary") or "").strip()
    if not summary:
        return fallback
    result = ["AI-саммари", summary]
    for key, title in (
        ("highlights", "Ключевые моменты"),
        ("decisions", "Решения"),
        ("next_steps", "Следующие шаги"),
        ("risks", "Риски"),
    ):
        values = data.get(key)
        if isinstance(values, list):
            clean = [str(value).strip() for value in values if str(value).strip()]
            if clean:
                result.extend(["", f"{title}:", *(f"• {value}" for value in clean[:6])])
    return "\n".join(result)[:3500]


async def run_meeting_reminders(
    session_factory,
    gateway,
    now: datetime | None = None,
    websocket_manager=None,
) -> int:
    now = now or datetime.now(UTC)
    soon = now + timedelta(minutes=REMINDER_LEAD_MINUTES)
    sent = 0
    async with session_factory() as session:
        rows = await session.execute(
            select(m.MeetingModel).where(
                m.MeetingModel.state == "scheduled",
                m.MeetingModel.scheduled_at.is_not(None),
                m.MeetingModel.scheduled_at <= soon,
                m.MeetingModel.scheduled_at >= now - timedelta(minutes=2),
            )
        )
        for meeting in rows.scalars():
            meta = meeting.metadata_json or {}
            if meta.get("reminded_5min"):
                continue
            team = await session.get(m.TeamModel, meeting.team_id)
            if team is not None and not (team.board_config or {}).get("meeting_reminders", True):
                continue
            tz = team.timezone if team else "Europe/Moscow"
            recipients = await _recipients(session, meeting, team)
            when = format_deadline(meeting.scheduled_at, tz)
            text = (
                f"⏰ Через ~5 минут созвон ({when}).\n"
                "Запускай даемон Grey Cardinal — он подключится к встрече."
            )
            for tg_id in recipients:
                await gateway.send_message(tg_id, text)
                sent += 1
            if websocket_manager is not None:
                await websocket_manager.broadcast(
                    {
                        "event": "meeting_reminder",
                        "payload": {
                            "meeting_id": str(meeting.id),
                            "public_id": meeting.public_id,
                            "team_id": str(meeting.team_id) if meeting.team_id else None,
                            "title": meeting.title,
                            "scheduled_at": meeting.scheduled_at.isoformat()
                            if meeting.scheduled_at
                            else None,
                        },
                    }
                )
            new_meta = dict(meta)
            new_meta["reminded_5min"] = True
            meeting.metadata_json = new_meta
        await session.commit()
    if sent:
        logger.info("Sent %d meeting 5-min reminders", sent)
    return sent


async def _recipients(session, meeting: m.MeetingModel, team: m.TeamModel | None) -> list[int]:
    rows = await session.execute(
        select(m.UserModel.telegram_user_id)
        .join(m.MeetingRsvpModel, m.MeetingRsvpModel.user_id == m.UserModel.id)
        .where(
            m.MeetingRsvpModel.meeting_id == meeting.id,
            m.MeetingRsvpModel.status == "yes",
            m.UserModel.telegram_user_id.is_not(None),
        )
    )
    yes_ids = [r[0] for r in rows.all()]
    if yes_ids:
        return yes_ids
    if team is None:
        return []
    rows = await session.execute(
        select(m.UserModel.telegram_user_id)
        .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
        .where(
            m.TeamMemberModel.team_id == team.id,
            m.UserModel.telegram_user_id.is_not(None),
        )
    )
    return [r[0] for r in rows.all()]
