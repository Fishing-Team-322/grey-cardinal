"""Internal endpoints для telegram-bot: message / callback / command."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from grey_cardinal_contracts import (
    ActionsResponse,
    AnswerCallbackAction,
    SendMessageAction,
    TelegramCallbackEvent,
    TelegramCommandEvent,
    TelegramMessageEvent,
)

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.application.rendering import CB_CONFIRM, CB_EDIT, CB_REJECT, EDIT_STUB_TEXT
from brain_api.application.use_cases.confirm_task import ConfirmTask
from brain_api.application.use_cases.ingest_chat_message import IngestChatMessage
from brain_api.application.use_cases.list_tasks import ListTasks
from brain_api.application.use_cases.reject_task import RejectTask
from brain_api.application.use_cases.send_evening_digest import SendEveningDigest
from brain_api.application.use_cases.update_task_status import UpdateTaskStatus
from brain_api.container import Container

router = APIRouter(
    prefix="/internal/telegram",
    tags=["internal-telegram"],
    dependencies=[Depends(verify_internal_token)],
)

_STATUS_COMMANDS = {"start_task", "block", "done"}
_HELP_TEXT = (
    "🧠 Grey Cardinal на связи.\n\n"
    "Я нахожу задачи в сообщениях чата и предлагаю создать карточки.\n\n"
    "Команды:\n"
    "/tasks — активные задачи\n"
    "/start_task GC-12 — взять в работу\n"
    "/block GC-12 — заблокировать\n"
    "/done GC-12 — закрыть\n"
    "/digest — вечерний дайджест сейчас"
)


@router.post("/message", response_model=ActionsResponse)
async def ingest_message(
    event: TelegramMessageEvent,
    container: Container = Depends(get_container),
) -> ActionsResponse:
    async with container.make_uow() as uow:
        use_case = IngestChatMessage(
            uow, container.extractor, container.event_publisher, container.config
        )
        return await use_case.execute(event)


@router.post("/callback", response_model=ActionsResponse)
async def ingest_callback(
    event: TelegramCallbackEvent,
    container: Container = Depends(get_container),
) -> ActionsResponse:
    action, target_id = _parse_callback(event.data)
    chat_id = event.message.chat_id
    message_id = event.message.message_id

    if action == CB_EDIT:
        return ActionsResponse(
            actions=[
                AnswerCallbackAction(
                    callback_query_id=event.callback_query_id,
                    text=EDIT_STUB_TEXT,
                    show_alert=True,
                )
            ]
        )

    if target_id is None:
        return ActionsResponse(
            actions=[
                AnswerCallbackAction(
                    callback_query_id=event.callback_query_id, text="Некорректные данные"
                )
            ]
        )

    async with container.make_uow() as uow:
        if action == CB_CONFIRM:
            return await ConfirmTask(
                uow, container.board, container.event_publisher, container.config
            ).execute(
                confirmation_id=target_id,
                callback_query_id=event.callback_query_id,
                chat_id=chat_id,
                message_id=message_id,
                actor_telegram_id=event.from_user.id,
            )
        if action == CB_REJECT:
            return await RejectTask(uow, container.event_publisher).execute(
                confirmation_id=target_id,
                callback_query_id=event.callback_query_id,
                chat_id=chat_id,
                message_id=message_id,
                actor_telegram_id=event.from_user.id,
            )

    return ActionsResponse(
        actions=[
            AnswerCallbackAction(
                callback_query_id=event.callback_query_id, text="Неизвестное действие"
            )
        ]
    )


@router.post("/command", response_model=ActionsResponse)
async def ingest_command(
    event: TelegramCommandEvent,
    container: Container = Depends(get_container),
) -> ActionsResponse:
    command = event.command.lower()
    chat_id = event.chat.id

    async with container.make_uow() as uow:
        if command in _STATUS_COMMANDS:
            return await UpdateTaskStatus(
                uow, container.board, container.event_publisher, container.config
            ).execute(command, event.args, chat_id)
        if command == "tasks":
            return await ListTasks(uow, container.config).execute(chat_id)
        if command == "digest":
            return await SendEveningDigest(
                uow, container.telegram_gateway, container.config
            ).as_actions(chat_id)

    if command in {"start", "help"}:
        return ActionsResponse(actions=[SendMessageAction(chat_id=chat_id, text=_HELP_TEXT)])

    return ActionsResponse(
        actions=[
            SendMessageAction(
                chat_id=chat_id,
                text=f"Неизвестная команда /{command}. Напиши /help для справки.",
            )
        ]
    )


def _parse_callback(data: str) -> tuple[str, UUID | None]:
    if ":" not in data:
        return data, None
    action, _, raw_id = data.partition(":")
    try:
        return action, UUID(raw_id)
    except ValueError:
        return action, None
