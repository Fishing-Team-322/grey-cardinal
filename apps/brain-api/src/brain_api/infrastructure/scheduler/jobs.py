"""Задания планировщика: собирают UoW и вызывают reminder/digest use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from brain_api.container import Container


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
        await SendMorningTaskSummary(
            uow, container.telegram_gateway, container.config
        ).execute()


async def run_meeting_5min_reminders(container: Container) -> None:
    await run_meeting_reminders(container.session_factory, container.telegram_gateway)


async def run_meeting_finalize_job(container: Container) -> None:
    await run_meeting_finalize(container.session_factory, container.telegram_gateway)


def register_jobs(scheduler, container: Container) -> None:
    """Зарегистрировать все P0-задания в планировщике."""
    scheduler.every(300, lambda: run_deadline_reminders(container), name="deadline_reminders")
    scheduler.every(1800, lambda: run_stale_reminders(container), name="stale_reminders")
    scheduler.every(60, lambda: run_meeting_5min_reminders(container), name="meeting_reminders")
    scheduler.every(60, lambda: run_meeting_finalize_job(container), name="meeting_finalize")
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
