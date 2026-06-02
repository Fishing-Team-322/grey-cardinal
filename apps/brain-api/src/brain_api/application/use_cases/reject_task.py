"""Use case: отклонение proposal."""

from __future__ import annotations

from uuid import UUID, uuid4

from brain_api.application.ports import EventPublisher, UnitOfWork
from brain_api.application.rendering import render_task_rejected
from brain_api.domain.entities import AuditLog
from brain_api.domain.enums import ConfirmationStatus
from grey_cardinal_contracts import (
    ActionsResponse,
    AnswerCallbackAction,
    EditMessageAction,
    EventName,
    WebsocketEvent,
)


class RejectTask:
    def __init__(self, uow: UnitOfWork, events: EventPublisher) -> None:
        self._uow = uow
        self._events = events

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
            return _answer(callback_query_id, "Предложение не найдено")

        if confirmation.status == ConfirmationStatus.accepted:
            await uow.commit()
            return _answer(callback_query_id, "Задача уже создана, отклонить нельзя")

        if confirmation.status == ConfirmationStatus.rejected:
            await uow.commit()
            return _rejected_actions(callback_query_id, chat_id, message_id)

        confirmation.status = ConfirmationStatus.rejected
        await uow.confirmations.update(confirmation)

        await uow.audit.add(
            AuditLog(
                id=uuid4(),
                actor_type="user",
                actor_id=str(actor_telegram_id) if actor_telegram_id else None,
                action="task_rejected",
                entity_type="confirmation",
                entity_id=confirmation.id,
                payload={"proposal_id": str(confirmation.proposal_id)},
            )
        )
        await self._events.publish(
            WebsocketEvent(
                event=EventName.task_rejected,
                payload={"confirmation_id": str(confirmation.id)},
            )
        )
        await uow.commit()
        return _rejected_actions(callback_query_id, chat_id, message_id)


def _answer(callback_query_id: str, text: str) -> ActionsResponse:
    return ActionsResponse(
        actions=[AnswerCallbackAction(callback_query_id=callback_query_id, text=text)]
    )


def _rejected_actions(callback_query_id: str, chat_id: int, message_id: int) -> ActionsResponse:
    return ActionsResponse(
        actions=[
            AnswerCallbackAction(callback_query_id=callback_query_id, text="Отклонено"),
            EditMessageAction(chat_id=chat_id, message_id=message_id, text=render_task_rejected()),
        ]
    )
