"""Use case: персональные вечерние дайджесты (каждому — список его задач).

В отличие от общего `SendEveningDigest`, здесь для каждого пользователя с
активными задачами собирается личная сводка (активные / просроченные / зависшие /
закрытые сегодня) и отправляется в личку. Если личка недоступна (нет
telegram_user_id) — сводка уходит в рабочий чат с упоминанием имени.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import TelegramGateway, UnitOfWork
from brain_api.application.rendering import render_personal_digest
from brain_api.application.use_cases.send_deadline_reminders import _default_chat_id
from brain_api.domain.entities import DigestLog, Task
from grey_cardinal_contracts import ActionsResponse, SendMessageAction

logger = logging.getLogger(__name__)


class _UserDigest:
    __slots__ = ("active", "overdue", "completed_today", "stale")

    def __init__(self) -> None:
        self.active: list[Task] = []
        self.overdue: list[Task] = []
        self.completed_today: list[Task] = []
        self.stale: list[Task] = []


class SendPersonalEveningDigests:
    def __init__(self, uow: UnitOfWork, telegram: TelegramGateway, config: AppConfig) -> None:
        self._uow = uow
        self._telegram = telegram
        self._config = config

    # ------------------------------------------------------------------ #
    async def _collect(self, now: datetime) -> dict[UUID, _UserDigest]:
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        active = await self._uow.tasks.list_active()
        completed = await self._uow.tasks.list_completed_since(start_of_day)
        stale_hours = self._config.reminder_stale_hours

        stale_threshold = _naive(now) - timedelta(hours=stale_hours)

        per_user: dict[UUID, _UserDigest] = defaultdict(_UserDigest)
        for task in active:
            if task.assignee_id is None:
                continue
            bucket = per_user[task.assignee_id]
            bucket.active.append(task)
            if task.deadline is not None and _naive(task.deadline) < _naive(now):
                bucket.overdue.append(task)
            reference = task.last_status_update_at or task.updated_at or task.created_at
            if reference is not None and _naive(reference) <= stale_threshold:
                bucket.stale.append(task)
        for task in completed:
            if task.assignee_id is None:
                continue
            per_user[task.assignee_id].completed_today.append(task)
        return per_user

    async def execute(self) -> int:
        """Запуск планировщиком: персональный дайджест каждому пользователю."""
        uow = self._uow
        now = self._config.now()
        default_chat_id = await _default_chat_id(uow, self._config)
        per_user = await self._collect(now)

        sent = 0
        for user_id, bucket in per_user.items():
            user = await uow.users.get(user_id)
            if user is None:
                continue
            text = render_personal_digest(
                user.display_name,
                bucket.active,
                bucket.overdue,
                bucket.completed_today,
                bucket.stale,
                self._config.timezone,
            )
            if user.telegram_user_id is not None:
                if await uow.digests.sent_today_for_user(user.telegram_user_id, now):
                    continue
                await self._telegram.send_message(user.telegram_user_id, text)
                await uow.digests.add(
                    DigestLog(
                        id=uuid4(),
                        telegram_user_id=user.telegram_user_id,
                        payload={"text": text},
                    )
                )
                sent += 1
            elif default_chat_id is not None:
                await self._telegram.send_message(default_chat_id, text)
                await uow.digests.add(
                    DigestLog(
                        id=uuid4(),
                        telegram_chat_id=default_chat_id,
                        payload={"text": text, "user": user.display_name},
                    )
                )
                sent += 1

        await uow.commit()
        if sent:
            logger.info("Sent %d personal evening digests", sent)
        return sent

    async def as_actions_for_user(self, telegram_user_id: int, chat_id: int) -> ActionsResponse:
        """Запуск командой /digest в личке: личная сводка пользователя."""
        uow = self._uow
        now = self._config.now()
        user = await uow.users.get_by_telegram_id(telegram_user_id)
        if user is None:
            return ActionsResponse(
                actions=[
                    SendMessageAction(
                        chat_id=chat_id,
                        text="У тебя пока нет задач в Grey Cardinal.",
                    )
                ]
            )
        bucket = (await self._collect(now)).get(user.id, _UserDigest())
        text = render_personal_digest(
            user.display_name,
            bucket.active,
            bucket.overdue,
            bucket.completed_today,
            bucket.stale,
            self._config.timezone,
        )
        await uow.digests.add(
            DigestLog(id=uuid4(), telegram_user_id=telegram_user_id, payload={"text": text})
        )
        await uow.commit()
        return ActionsResponse(actions=[SendMessageAction(chat_id=chat_id, text=text)])


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)
