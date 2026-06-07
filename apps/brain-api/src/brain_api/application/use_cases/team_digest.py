"""Дайджест задач команды по расписанию (per-team), управляется через /settings.

Запускается планировщиком; для каждой команды с привязанным чатом и включённым
режимом дайджеста проверяет, попадает ли текущий час (в таймзоне команды) в слот,
и если за этот слот сегодня ещё не слали — отправляет сводку активных задач.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from brain_api.application.rendering import format_deadline
from brain_api.application.use_cases.team_settings import digest_slots
from brain_api.infrastructure.db import models as m

logger = logging.getLogger(__name__)

_ACTIVE = ("todo", "in_progress", "blocked", "review")


def render_team_digest(team_name: str, tasks: list, tz: str) -> str:
    lines = [f"📋 Дайджест задач — {team_name}", ""]
    if not tasks:
        lines.append("Активных задач нет. 🎉")
        return "\n".join(lines)
    for t in tasks:
        who = t.assignee_text or "—"
        lines.append(f"• {t.public_id} [{t.status}] {t.title}")
        lines.append(f"   {who} · дедлайн: {format_deadline(t.deadline, tz)}")
    lines.append("")
    lines.append(f"Всего активных: {len(tasks)}")
    return "\n".join(lines)


async def run_team_digests(session_factory, gateway, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    sent = 0
    async with session_factory() as session:
        teams = (
            await session.execute(select(m.TeamModel).where(m.TeamModel.tg_chat_id.is_not(None)))
        ).scalars().all()
        for team in teams:
            cfg = team.board_config or {}
            mode = cfg.get("digest_mode", "off")
            if mode == "off":
                continue
            slots = cfg.get("digest_hours") or digest_slots(mode)
            if not slots:
                continue
            local = now.astimezone(ZoneInfo(team.timezone))
            if local.hour not in slots:
                continue
            today = local.date()
            logs = (
                await session.execute(
                    select(m.DigestLogModel).where(
                        m.DigestLogModel.team_id == team.id, m.DigestLogModel.date == today
                    )
                )
            ).scalars().all()
            done = {(log.payload or {}).get("slot") for log in logs}
            if local.hour in done:
                continue
            tasks = (
                await session.execute(
                    select(m.TaskModel)
                    .where(m.TaskModel.team_id == team.id, m.TaskModel.status.in_(_ACTIVE))
                    .order_by(m.TaskModel.deadline.is_(None), m.TaskModel.deadline)
                )
            ).scalars().all()
            await gateway.send_message(
                team.tg_chat_id, render_team_digest(team.name, list(tasks), team.timezone)
            )
            session.add(
                m.DigestLogModel(
                    team_id=team.id, telegram_chat_id=team.tg_chat_id,
                    date=today, timezone=team.timezone, payload={"slot": local.hour},
                )
            )
            sent += 1
        await session.commit()
    if sent:
        logger.info("Sent %d team digests", sent)
    return sent
