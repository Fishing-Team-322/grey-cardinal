"""Use case: напоминания о близком дедлайне (запускается планировщиком каждые 5 минут).

Доставка адресная: в личку исполнителю (если есть telegram_user_id) или в рабочий
чат. Применяется анти-спам политика (quiet hours / лимит в день / интервал).
"""

from __future__ import annotations

import logging
from uuid import uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import EventPublisher, TelegramGateway, UnitOfWork
from brain_api.application.reminder_policy import (
    ReminderRecipient,
    check_anti_spam,
    resolve_recipient,
)
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
        default_chat_id = await _default_chat_id(uow, self._config)

        tasks = await uow.tasks.list_for_deadline_reminder(
            now, self._config.reminder_deadline_hours_before
        )
        sent = 0
        for task in tasks:
            # Дедлайн-напоминание по одной задаче не дублируем.
            if await uow.reminders.exists(task.id, ReminderKind.deadline):
                continue

            recipient = await resolve_recipient(uow, task, default_chat_id)
            if recipient is None:
                continue

            reason = await check_anti_spam(uow, self._config, now, recipient)
            if reason is not None:
                await _publish_suppressed(self._events, reason, task, recipient)
                continue

            text = render_deadline_reminder(task, self._config.timezone)
            if not recipient.is_private and recipient.mention:
                text = f"{recipient.mention}\n\n{text}"
            await self._telegram.send_message(recipient.chat_id, text)
            await uow.reminders.add(
                ReminderLog(
                    id=uuid4(),
                    task_id=task.id,
                    kind=ReminderKind.deadline,
                    recipient_telegram_user_id=recipient.user_id,
                    telegram_chat_id=recipient.chat_id,
                    payload={"public_id": task.public_id, "private": recipient.is_private},
                )
            )
            await self._events.publish(
                WebsocketEvent(
                    event=EventName.reminder_sent,
                    payload={
                        "kind": "deadline",
                        "public_id": task.public_id,
                        "private": recipient.is_private,
                    },
                )
            )
            sent += 1

        await uow.commit()
        if sent:
            logger.info("Sent %d deadline reminders", sent)
        return sent


async def _publish_suppressed(
    events: EventPublisher,
    reason: str,
    task,
    recipient: ReminderRecipient,
) -> None:
    await events.publish(
        WebsocketEvent(
            event=EventName.reminder_suppressed,
            payload={
                "reason": reason,
                "task_public_id": task.public_id,
                "user_id": str(recipient.user_id) if recipient.user_id else None,
            },
        )
    )


async def _default_chat_id(uow: UnitOfWork, config: AppConfig | None = None) -> int | None:
    if config and config.default_telegram_chat_id is not None:
        return config.default_telegram_chat_id
    project = await uow.projects.ensure_default(
        config.default_workspace_name if config else "Hackathon Team"
    )
    if project.default_chat_id is None:
        return None
    chat = await uow.chats.get(project.default_chat_id)
    return chat.telegram_chat_id if chat else None
