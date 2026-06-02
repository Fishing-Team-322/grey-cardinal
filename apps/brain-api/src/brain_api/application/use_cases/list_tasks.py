"""Use case: список активных задач (/tasks)."""

from __future__ import annotations

from grey_cardinal_contracts import ActionsResponse, SendMessageAction

from brain_api.application.config import AppConfig
from brain_api.application.ports import UnitOfWork
from brain_api.application.rendering import render_task_list
from brain_api.domain.entities import Task


class ListTasks:
    def __init__(self, uow: UnitOfWork, config: AppConfig) -> None:
        self._uow = uow
        self._config = config

    async def execute(self, chat_id: int) -> ActionsResponse:
        tasks = await self._uow.tasks.list_active()
        text = render_task_list(tasks, self._config.timezone)
        return ActionsResponse(actions=[SendMessageAction(chat_id=chat_id, text=text)])

    async def list_active(self) -> list[Task]:
        return await self._uow.tasks.list_active()
