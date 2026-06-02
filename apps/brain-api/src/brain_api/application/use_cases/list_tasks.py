"""Use case: список активных задач (/tasks)."""

from __future__ import annotations

from brain_api.application.config import AppConfig
from brain_api.application.ports import UnitOfWork
from brain_api.application.rendering import render_task_list
from brain_api.domain.entities import Task
from grey_cardinal_contracts import ActionsResponse, SendMessageAction


class ListTasks:
    def __init__(self, uow: UnitOfWork, config: AppConfig) -> None:
        self._uow = uow
        self._config = config

    async def execute(self, chat_id: int) -> ActionsResponse:
        tasks = await self._uow.tasks.list_active_for_chat(chat_id)
        text = render_task_list(tasks, self._config.timezone)
        return ActionsResponse(actions=[SendMessageAction(chat_id=chat_id, text=text)])

    async def list_active(self, chat_id: int | None = None) -> list[Task]:
        if chat_id is None:
            return await self._uow.tasks.list_active()
        return await self._uow.tasks.list_active_for_chat(chat_id)
