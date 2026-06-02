"""Задания планировщика: собирают UoW и вызывают reminder/digest use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from brain_api.application.use_cases.send_deadline_reminders import SendDeadlineReminders
from brain_api.application.use_cases.send_evening_digest import SendEveningDigest
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
    async with container.make_uow() as uow:
        await SendEveningDigest(uow, container.telegram_gateway, container.config).execute()


def register_jobs(scheduler, container: Container) -> None:
    """Зарегистрировать все P0-задания в планировщике."""
    scheduler.every(300, lambda: run_deadline_reminders(container), name="deadline_reminders")
    scheduler.every(1800, lambda: run_stale_reminders(container), name="stale_reminders")
    scheduler.daily_at(
        container.config.evening_digest_hour,
        lambda: run_evening_digest(container),
        name="evening_digest",
    )
