"""Use case: напоминания о близком дедлайне (запускается планировщиком каждые 5 минут)."""

from __future__ import annotations

import logging
from uuid import uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import EventPublisher, TelegramGateway, UnitOfWork
from brain_api.application.rendering import render_deadline_reminder
from brain_api.domain.entities import ReminderLog
from brain_api.domain.enums import ReminderKind
from grey_cardinal_contracts import EventName, WebsocketEvent

logger = logging.getLogger(__name__)


class SendDeadlineReminders:
    def __init__(
        self,
        uow: UnitOfWork,
        telegram: TelegramGateway,
        events: EventPublisher,
        config: AppConfig,
    ) -> None:
        self._uow = uow
        self._telegram = telegram
        self._events = events
        self._config = config

    async def execute(self) -> int:
        uow = self._uow
        now = self._config.now()
        chat_id = await _default_chat_id(uow)
        if chat_id is None:
            return 0

        tasks = await uow.tasks.list_for_deadline_reminder(
            now, self._config.reminder_deadline_hours_before
        )
        sent = 0
        for task in tasks:
            if await uow.reminders.exists(task.id, ReminderKind.deadline):
                continue
            text = render_deadline_reminder(task, self._config.timezone)
            await self._telegram.send_message(chat_id, text)
            await uow.reminders.add(
                ReminderLog(
                    id=uuid4(),
                    task_id=task.id,
                    kind=ReminderKind.deadline,
                    telegram_chat_id=chat_id,
                    payload={"public_id": task.public_id},
                )
            )
            await self._events.publish(
                WebsocketEvent(
                    event=EventName.reminder_sent,
                    payload={"kind": "deadline", "public_id": task.public_id},
                )
            )
            sent += 1

        await uow.commit()
        if sent:
            logger.info("Sent %d deadline reminders", sent)
        return sent


async def _default_chat_id(uow: UnitOfWork) -> int | None:
    project = await uow.projects.ensure_default()
    if project.default_chat_id is None:
        return None
    chat = await uow.chats.get(project.default_chat_id)
    return chat.telegram_chat_id if chat else None
