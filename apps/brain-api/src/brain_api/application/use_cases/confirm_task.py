"""Use case: подтверждение proposal -> создание задачи и карточки на доске."""

from __future__ import annotations

from uuid import UUID

from brain_api.application.config import AppConfig
from brain_api.application.ports import BoardGateway, EventPublisher, UnitOfWork
from brain_api.application.rendering import render_task_created
from brain_api.application.use_cases._shared import create_task_from_proposal
from brain_api.domain.entities import Task
from brain_api.domain.enums import ConfirmationStatus
from grey_cardinal_contracts import (
    ActionsResponse,
    AnswerCallbackAction,
    EditMessageAction,
)


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

        task, provider_label = await create_task_from_proposal(
            uow,
            self._board,
            self._events,
            self._config,
            proposal,
            confirmation=confirmation,
            actor_telegram_id=actor_telegram_id,
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
        )

        await uow.commit()
        return _created_actions(
            task, callback_query_id, chat_id, message_id, self._config, provider_label
        )


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
