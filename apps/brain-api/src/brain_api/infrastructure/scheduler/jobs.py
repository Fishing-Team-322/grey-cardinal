"""Задания планировщика: собирают UoW и вызывают reminder/digest use cases."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from brain_api.application.use_cases.meeting_reminders import (
    run_meeting_finalize,
    run_meeting_reminders,
)
from brain_api.application.use_cases.send_deadline_reminders import SendDeadlineReminders
from brain_api.application.use_cases.send_morning_task_summary import SendMorningTaskSummary
from brain_api.application.use_cases.send_personal_evening_digests import (
    SendPersonalEveningDigests,
)
from brain_api.application.use_cases.send_stale_status_reminders import SendStaleStatusReminders
from brain_api.application.use_cases.team_digest import run_team_digests
from brain_api.application.use_cases.yougile_discovery import discover_yougile_workspace
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher

if TYPE_CHECKING:
    from brain_api.container import Container

logger = logging.getLogger(__name__)


async def run_deadline_reminders(container: Container) -> None:
    async with container.make_uow() as uow:
        await SendDeadlineReminders(
            uow, container.telegram_gateway, container.event_publisher, container.config
        ).execute()


async def run_stale_reminders(container: Container) -> None:
    async with container.make_uow() as uow:
        await SendStaleStatusReminders(
            uow, container.telegram_gateway, container.event_publisher, container.config
        ).execute()


async def run_evening_digest(container: Container) -> None:
    # Планировщик рассылает персональные дайджесты каждому пользователю с задачами.
    async with container.make_uow() as uow:
        await SendPersonalEveningDigests(
            uow, container.telegram_gateway, container.config
        ).execute()


async def run_morning_task_summary(container: Container) -> None:
    async with container.make_uow() as uow:
        await SendMorningTaskSummary(uow, container.telegram_gateway, container.config).execute()


async def run_meeting_5min_reminders(container: Container) -> None:
    await run_meeting_reminders(container.session_factory, container.telegram_gateway)


async def run_meeting_finalize_job(container: Container) -> None:
    await run_meeting_finalize(container.session_factory, container.telegram_gateway)


async def run_team_digests_job(container: Container) -> None:
    await run_team_digests(container.session_factory, container.telegram_gateway)


async def run_yougile_discovery_job(container: Container) -> None:
    settings = container.settings
    cipher = SecretCipher(settings.board_creds_encryption_key or "dev-key")
    async with container.session_factory() as session:
        team_ids = list(
            (
                await session.execute(
                    select(m.TeamModel.id).where(
                        m.TeamModel.board_provider == "yougile",
                        m.TeamModel.board_credentials_encrypted.is_not(None),
                    )
                )
            ).scalars()
        )
    for team_id in team_ids:
        try:
            await discover_yougile_workspace(
                container.session_factory,
                team_id=team_id,
                api_base_url=settings.yougile_api_base_url,
                cipher=cipher,
            )
        except Exception:
            logger.exception("Scheduled YouGile discovery failed for team %s", team_id)


def register_jobs(scheduler, container: Container) -> None:
    """Зарегистрировать все P0-задания в планировщике."""
    scheduler.every(300, lambda: run_deadline_reminders(container), name="deadline_reminders")
    scheduler.every(1800, lambda: run_stale_reminders(container), name="stale_reminders")
    scheduler.every(60, lambda: run_meeting_5min_reminders(container), name="meeting_reminders")
    scheduler.every(60, lambda: run_meeting_finalize_job(container), name="meeting_finalize")
    scheduler.every(900, lambda: run_team_digests_job(container), name="team_digests")
    scheduler.every(
        container.settings.yougile_discovery_schedule_hours * 3600,
        lambda: run_yougile_discovery_job(container),
        name="yougile_discovery",
    )
    scheduler.daily_at(
        container.config.morning_summary_hour,
        lambda: run_morning_task_summary(container),
        name="morning_task_summary",
    )
    scheduler.daily_at(
        container.config.evening_digest_hour,
        lambda: run_evening_digest(container),
        name="evening_digest",
    )
