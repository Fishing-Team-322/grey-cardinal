"""Use case: напоминания о «зависших» задачах (планировщик, каждые 30 минут).

Адресная доставка исполнителю + анти-спам политика. Stale-напоминание по задаче
не чаще одного раза за stale-окно.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import EventPublisher, TelegramGateway, UnitOfWork
from brain_api.application.reminder_policy import (
    check_anti_spam,
    resolve_recipient,
)
from brain_api.application.rendering import render_stale_reminder
from brain_api.application.use_cases.send_deadline_reminders import (
    _default_chat_id,
    _publish_suppressed,
)
from brain_api.domain.entities import ReminderLog
from brain_api.domain.enums import ReminderKind
from grey_cardinal_contracts import EventName, WebsocketEvent

logger = logging.getLogger(__name__)


class SendStaleStatusReminders:
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
        default_chat_id = await _default_chat_id(uow, self._config)

        stale_hours = self._config.reminder_stale_hours
        tasks = await uow.tasks.list_stale(now, stale_hours)
        cooldown = now - timedelta(hours=stale_hours)
        sent = 0
        for task in tasks:
            # Stale-напоминание не чаще одного раза за stale-окно.
            last = await uow.reminders.last_sent_at(task.id, ReminderKind.stale)
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=now.tzinfo)
            if last is not None and last > cooldown:
                continue

            recipient = await resolve_recipient(uow, task, default_chat_id)
            if recipient is None:
                continue

            reason = await check_anti_spam(uow, self._config, now, recipient)
            if reason is not None:
                await _publish_suppressed(self._events, reason, task, recipient)
                continue

            text = render_stale_reminder(task)
            await self._telegram.send_message(recipient.chat_id, text)
            await uow.reminders.add(
                ReminderLog(
                    id=uuid4(),
                    task_id=task.id,
                    kind=ReminderKind.stale,
                    recipient_telegram_user_id=recipient.user_id,
                    telegram_chat_id=recipient.chat_id,
                    payload={"public_id": task.public_id, "private": recipient.is_private},
                )
            )
            await self._events.publish(
                WebsocketEvent(
                    event=EventName.reminder_sent,
                    payload={
                        "kind": "stale",
                        "public_id": task.public_id,
                        "private": recipient.is_private,
                    },
                )
            )
            sent += 1

        await uow.commit()
        if sent:
            logger.info("Sent %d stale reminders", sent)
        return sent
