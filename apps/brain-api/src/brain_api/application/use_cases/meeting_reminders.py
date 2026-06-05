"""Напоминание о созвоне за ~5 минут до начала (планировщик, каждую минуту).

Шлёт в личку каждому, кто отметился «Приду» (а если RSVP пуст — всем участникам
команды с привязанным Telegram), что пора запускать даемон Grey Cardinal.
Дедупликация — через флаг `metadata_json.reminded_5min` на самом созвоне.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from brain_api.application.rendering import format_deadline
from brain_api.infrastructure.db import models as m

logger = logging.getLogger(__name__)

REMINDER_LEAD_MINUTES = 5


async def run_meeting_reminders(session_factory, gateway, now: datetime | None = None) -> int:
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
