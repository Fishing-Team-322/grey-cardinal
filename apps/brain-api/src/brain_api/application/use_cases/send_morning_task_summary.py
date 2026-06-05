"""Use case: утренняя сводка по активным задачам в рабочий чат."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from brain_api.application.config import AppConfig
from brain_api.application.ports import TelegramGateway, UnitOfWork
from brain_api.application.rendering import format_deadline, status_label
from brain_api.application.use_cases.send_deadline_reminders import _default_chat_id
from brain_api.domain.entities import Task, User

logger = logging.getLogger(__name__)


class SendMorningTaskSummary:
    def __init__(self, uow: UnitOfWork, telegram: TelegramGateway, config: AppConfig) -> None:
        self._uow = uow
        self._telegram = telegram
        self._config = config

    async def execute(self) -> int:
        chat_id = await _default_chat_id(self._uow, self._config)
        if chat_id is None:
            return 0

        tasks = await self._uow.tasks.list_active()
        text = await self._render(tasks)
        await self._telegram.send_message(chat_id, text)
        await self._uow.commit()
        logger.info("Morning task summary sent to chat %s", chat_id)
        return 1

    async def _render(self, tasks: list[Task]) -> str:
        now = self._config.now()
        lines = ["☀️ Утренняя сверка задач", ""]
        if not tasks:
            lines.append("Активных задач нет.")
            return "\n".join(lines)

        users: dict[str, User] = {}
        for task in tasks:
            if task.assignee_id is not None:
                user = await self._uow.users.get(task.assignee_id)
                if user is not None:
                    users[str(task.assignee_id)] = user

        soon_deadline: list[str] = []
        for task in tasks:
            user = users.get(str(task.assignee_id)) if task.assignee_id else None
            assignee = _mention(user, task.assignee_text)
            deadline = format_deadline(task.deadline, self._config.timezone, now)
            lines.append(
                f"{task.public_id} [{status_label(task.status)}] {task.title} "
                f"— {assignee}, дедлайн: {deadline}"
            )
            if _is_deadline_soon(task.deadline, now, self._config):
                soon_deadline.append(f"{assignee}: {task.public_id} до {deadline}")

        if soon_deadline:
            lines.append("")
            lines.append("Скоро дедлайн:")
            lines.extend(soon_deadline)

        return "\n".join(lines)


def _mention(user: User | None, fallback: str | None) -> str:
    if user is not None and user.telegram_username:
        return f"@{user.telegram_username}"
    return fallback or "не определён"


def _is_deadline_soon(deadline: datetime | None, now: datetime, config: AppConfig) -> bool:
    if deadline is None:
        return False
    current = now
    target = deadline
    if target.tzinfo is None and current.tzinfo is not None:
        target = target.replace(tzinfo=current.tzinfo)
    if current.tzinfo is None and target.tzinfo is not None:
        current = current.replace(tzinfo=target.tzinfo)
    return target <= current + timedelta(hours=config.reminder_deadline_hours_before)
