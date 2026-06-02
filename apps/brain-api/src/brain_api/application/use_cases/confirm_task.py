"""Use case: подтверждение proposal -> создание задачи и карточки на доске."""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from grey_cardinal_contracts import (
    ActionsResponse,
    AnswerCallbackAction,
    EditMessageAction,
    EventName,
    WebsocketEvent,
)

from brain_api.application.config import AppConfig
from brain_api.application.ports import BoardGateway, EventPublisher, UnitOfWork
from brain_api.application.rendering import render_task_created
from brain_api.domain.entities import AuditLog, BoardCard, Confirmation, Task
from brain_api.domain.enums import BoardProvider, ConfirmationStatus, TaskStatus
from brain_api.domain.errors import BoardError
from brain_api.domain.services import format_public_id

logger = logging.getLogger(__name__)

_PROVIDER_LABEL = {BoardProvider.mock: "Mock", BoardProvider.yougile: "YouGile"}


class ConfirmTask:
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

    async def execute(
        self,
        confirmation_id: UUID,
        callback_query_id: str,
        chat_id: int,
        message_id: int,
        actor_telegram_id: int | None = None,
    ) -> ActionsResponse:
        uow = self._uow
        confirmation = await uow.confirmations.get(confirmation_id)
        if confirmation is None:
            return _just_answer(callback_query_id, "Предложение не найдено")

        # Идемпотентность: повторный confirm не создаёт дубль.
        if confirmation.status == ConfirmationStatus.accepted and confirmation.created_task_id:
            task = await uow.tasks.get(confirmation.created_task_id)
            await uow.commit()
            if task is None:
                return _just_answer(callback_query_id, "Задача уже создана")
            return _created_actions(task, callback_query_id, chat_id, message_id, self._config)

        if confirmation.status in (ConfirmationStatus.rejected, ConfirmationStatus.expired):
            await uow.commit()
            return _just_answer(callback_query_id, "Предложение уже закрыто")

        proposal = await uow.proposals.get(confirmation.proposal_id)
        if proposal is None:
            return _just_answer(callback_query_id, "Исходное предложение не найдено")

        project = await uow.projects.ensure_default()
        sequence = await uow.tasks.next_sequence()
        now = self._config.now()
        task = Task(
            id=uuid4(),
            public_id=format_public_id(sequence),
            title=proposal.title,
            description=proposal.description,
            status=TaskStatus.todo,
            priority=proposal.priority,
            source=proposal.source,
            project_id=project.id,
            assignee_id=proposal.assignee_id,
            assignee_text=proposal.assignee_text,
            deadline=proposal.deadline,
            source_message_id=proposal.source_message_id,
            created_from_proposal_id=proposal.id,
            last_status_update_at=now,
        )
        await uow.tasks.add(task)

        provider_label = await self._create_board_card(task)

        confirmation.status = ConfirmationStatus.accepted
        confirmation.created_task_id = task.id
        confirmation.telegram_chat_id = chat_id
        confirmation.telegram_message_id = message_id
        await uow.confirmations.update(confirmation)

        await uow.audit.add(
            AuditLog(
                id=uuid4(),
                actor_type="user",
                actor_id=str(actor_telegram_id) if actor_telegram_id else None,
                action="task_created",
                entity_type="task",
                entity_id=task.id,
                payload={"public_id": task.public_id, "board": provider_label},
            )
        )

        await self._events.publish(
            WebsocketEvent(
                event=EventName.task_created,
                payload={
                    "task_id": str(task.id),
                    "public_id": task.public_id,
                    "title": task.title,
                    "status": task.status.value,
                    "assignee": task.assignee_text,
                    "board": provider_label,
                },
            )
        )

        await uow.commit()
        return _created_actions(
            task, callback_query_id, chat_id, message_id, self._config, provider_label
        )

    async def _create_board_card(self, task: Task) -> str | None:
        """Создать карточку на доске. Ошибка доски не теряет задачу — пишем в audit."""
        try:
            result = await self._board.create_card(task)
        except BoardError as exc:
            logger.warning("Board card creation failed for %s: %s", task.public_id, exc)
            await self._uow.audit.add(
                AuditLog(
                    id=uuid4(),
                    actor_type="system",
                    action="board_card_failed",
                    entity_type="task",
                    entity_id=task.id,
                    payload={"error": str(exc)},
                )
            )
            return None

        provider = BoardProvider(result.provider.value)
        await self._uow.board_cards.add(
            BoardCard(
                id=uuid4(),
                task_id=task.id,
                provider=provider,
                external_card_id=result.external_card_id,
                external_url=result.external_url,
                external_payload=result.external_payload,
            )
        )
        return _PROVIDER_LABEL.get(provider, provider.value)


def _just_answer(callback_query_id: str, text: str) -> ActionsResponse:
    return ActionsResponse(
        actions=[AnswerCallbackAction(callback_query_id=callback_query_id, text=text)]
    )


def _created_actions(
    task: Task,
    callback_query_id: str,
    chat_id: int,
    message_id: int,
    config: AppConfig,
    provider_label: str | None = None,
) -> ActionsResponse:
    text = render_task_created(task, provider_label, config.timezone)
    return ActionsResponse(
        actions=[
            AnswerCallbackAction(callback_query_id=callback_query_id, text="Задача создана"),
            EditMessageAction(chat_id=chat_id, message_id=message_id, text=text),
        ]
    )
