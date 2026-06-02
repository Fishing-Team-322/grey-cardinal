"""Use case: смена статуса задачи (/start_task, /block, /done)."""

from __future__ import annotations

import logging
from uuid import uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import BoardGateway, EventPublisher, UnitOfWork
from brain_api.application.rendering import render_status_changed
from brain_api.application.use_cases.gamification import GamificationService
from brain_api.domain.entities import AuditLog, Task
from brain_api.domain.enums import TaskStatus, XpEventKind
from brain_api.domain.services import parse_public_id, status_for_command
from grey_cardinal_contracts import (
    ActionsResponse,
    EventName,
    SendMessageAction,
    WebsocketEvent,
)

logger = logging.getLogger(__name__)


class UpdateTaskStatus:
    def __init__(
        self,
        uow: UnitOfWork,
        board: BoardGateway,
        events: EventPublisher,
        config: AppConfig,
    ) -> None:
        self._uow = uow
        self._board = board
        self._events = events
        self._config = config

    async def execute(self, command: str, args: list[str], chat_id: int) -> ActionsResponse:
        new_status = status_for_command(command)
        if new_status is None:
            return _msg(chat_id, "Неизвестная команда изменения статуса.")

        if not args:
            return _msg(chat_id, f"Укажи задачу, например: /{command} GC-12")

        task = await self._resolve_task(args[0])
        if task is None:
            return _msg(chat_id, f"Задача {args[0]} не найдена.")

        now = self._config.now()
        task.status = new_status
        task.last_status_update_at = now
        if new_status == TaskStatus.done:
            task.completed_at = now
        await self._uow.tasks.update(task)

        await self._sync_board(task, new_status)

        await self._uow.audit.add(
            AuditLog(
                id=uuid4(),
                actor_type="user",
                action="task_status_changed",
                entity_type="task",
                entity_id=task.id,
                payload={"public_id": task.public_id, "status": new_status.value},
            )
        )
        await self._events.publish(
            WebsocketEvent(
                event=EventName.task_status_changed,
                payload={
                    "task_id": str(task.id),
                    "public_id": task.public_id,
                    "status": new_status.value,
                },
            )
        )
        if task.assignee_id is not None:
            await GamificationService().grant(
                self._uow,
                user_id=task.assignee_id,
                workspace_id=task.project_id,
                task_id=task.id,
                kind=XpEventKind.status_updated,
                reason=f"Обновил статус {task.public_id}: {new_status.value}",
                idempotency_key=f"status_updated:{task.id}:{new_status.value}",
            )
            if new_status == TaskStatus.done:
                await GamificationService().grant(
                    self._uow,
                    user_id=task.assignee_id,
                    workspace_id=task.project_id,
                    task_id=task.id,
                    kind=XpEventKind.task_completed,
                    reason=f"Закрыл задачу {task.public_id}",
                    idempotency_key=f"task_completed:{task.id}",
                )
        await self._uow.commit()
        return _msg(chat_id, render_status_changed(task))

    async def _resolve_task(self, ref: str) -> Task | None:
        sequence = parse_public_id(ref)
        if sequence is not None:
            from brain_api.domain.services import format_public_id

            task = await self._uow.tasks.get_by_public_id(format_public_id(sequence))
            if task is not None:
                return task
        # запасной путь: ref как UUID
        try:
            from uuid import UUID

            return await self._uow.tasks.get(UUID(ref))
        except (ValueError, AttributeError):
            return None

    async def _sync_board(self, task: Task, status: TaskStatus) -> None:
        card = await self._uow.board_cards.get_by_task(task.id)
        if card is None:
            return
        try:
            if status == TaskStatus.done:
                await self._board.close_card(card.external_card_id)
            else:
                await self._board.move_card(card.external_card_id, status)
        except Exception as exc:
            logger.warning("Board sync failed for %s: %s", task.public_id, exc)
            await self._uow.audit.add(
                AuditLog(
                    id=uuid4(),
                    actor_type="system",
                    action="board_sync_failed",
                    entity_type="task",
                    entity_id=task.id,
                    payload={"error": str(exc), "status": status.value},
                )
            )


def _msg(chat_id: int, text: str) -> ActionsResponse:
    return ActionsResponse(actions=[SendMessageAction(chat_id=chat_id, text=text)])
