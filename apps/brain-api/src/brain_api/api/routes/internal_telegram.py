"""Internal endpoints для telegram-bot: message / callback / command."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.application.rendering import CB_CONFIRM, CB_EDIT, CB_REJECT, EDIT_STUB_TEXT
from brain_api.application.use_cases.confirm_task import ConfirmTask
from brain_api.application.use_cases.ingest_chat_message import IngestChatMessage
from brain_api.application.use_cases.ingest_transcript_event import IngestTranscriptEvent
from brain_api.application.use_cases.list_tasks import ListTasks
from brain_api.application.use_cases.manage_meetings import (
    meeting_response,
    start_meeting,
    stop_meeting,
)
from brain_api.application.use_cases.reject_task import RejectTask
from brain_api.application.use_cases.send_evening_digest import SendEveningDigest
from brain_api.application.use_cases.update_task_status import UpdateTaskStatus
from brain_api.container import Container
from grey_cardinal_contracts import (
    ActionsResponse,
    AnswerCallbackAction,
    SendMessageAction,
    TelegramCallbackEvent,
    TelegramCommandEvent,
    TelegramMessageEvent,
    TranscriptEvent,
    TranscriptSource,
)

router = APIRouter(
    prefix="/internal/telegram",
    tags=["internal-telegram"],
    dependencies=[Depends(verify_internal_token)],
)

_STATUS_COMMANDS = {"start_task", "block", "done"}
_START_TEXT = (
    "Серый кардинал подключён.\n"
    "Я нахожу задачи в переписке и встречах, предлагаю создать карточки "
    "и напоминаю о дедлайнах."
)
_HELP_TEXT = (
    "Команды:\n"
    "/tasks — активные задачи\n"
    "/tasks_all — все активные задачи workspace\n"
    "/done GC-1 — закрыть задачу\n"
    "/start_task GC-1 — взять в работу\n"
    "/block GC-1 — заблокировать\n"
    "/digest — вечерний дайджест\n"
    "/bind_chat — привязать чат к workspace\n"
    "/meeting_start — начать встречу\n"
    "/meeting_stop — завершить встречу\n"
    "/meeting_status — показать активную встречу\n"
    "/demo_start — запустить демо-сценарий\n"
    "/demo_transcript — добавить тестовую реплику\n"
    "/demo_reset — очистить demo-встречи в dev"
)
_DEMO_LINES = [
    "Петя, подготовь оплату до завтра 18:00",
    "Аня, проверь интеграцию с YouGile сегодня вечером",
    "Дима, подними websocket для дашборда до завтра",
]


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
        if command == "tasks_all":
            tasks = await ListTasks(uow, container.config).list_active()
            from brain_api.application.rendering import render_task_list

            return ActionsResponse(
                actions=[
                    SendMessageAction(
                        chat_id=chat_id,
                        text=render_task_list(tasks, container.config.timezone),
                    )
                ]
            )
        if command == "digest":
            return await SendEveningDigest(
                uow, container.telegram_gateway, container.config
            ).as_actions(chat_id)
        if command == "bind_chat":
            project = await uow.projects.ensure_default(container.config.default_workspace_name)
            existing = await uow.chats.get_by_telegram_id(chat_id)
            already_bound = existing is not None and existing.project_id == project.id
            chat = await uow.chats.upsert(chat_id, event.chat.type, event.chat.title, project.id)
            await uow.projects.set_default_chat(project.id, chat.id)
            await uow.commit()
            prefix = "Этот чат уже привязан" if already_bound else "Чат привязан"
            return _text(chat_id, f"{prefix} к workspace: {project.name}")
        if command == "meeting_start":
            meeting = await start_meeting(
                uow,
                container.config,
                telegram_chat_id=chat_id,
                chat_type=event.chat.type,
                chat_title=event.chat.title,
                external_source="telegram",
            )
            await uow.commit()
            return _text(
                chat_id,
                f"Встреча начата: {meeting.public_id}\n"
                "Теперь transcript events будут привязываться к этой встрече.",
            )
        if command == "meeting_stop":
            active_meeting = await uow.meetings.get_active_for_chat(chat_id)
            if active_meeting is None:
                return _text(chat_id, "Сейчас нет активной встречи.")
            active_meeting = await stop_meeting(uow, container.config, active_meeting)
            await uow.commit()
            dto = await meeting_response(uow, active_meeting)
            return _text(
                chat_id,
                f"Встреча {active_meeting.public_id} завершена.\n"
                f"Реплик: {dto.transcript_count}\n"
                f"Извлечено задач: {dto.proposal_count}",
            )
        if command == "meeting_status":
            active_meeting = await uow.meetings.get_active_for_chat(chat_id)
            if active_meeting is None:
                return _text(chat_id, "Сейчас нет активной встречи.")
            dto = await meeting_response(uow, active_meeting)
            return _text(
                chat_id,
                f"Активная встреча: {active_meeting.public_id}\n"
                f"Старт: {active_meeting.started_at:%H:%M}\n"
                f"Реплик: {dto.transcript_count}\n"
                f"Извлечено задач: {dto.proposal_count}",
            )
        if command == "demo_start":
            meeting = await start_meeting(
                uow,
                container.config,
                telegram_chat_id=chat_id,
                chat_type=event.chat.type,
                chat_title=event.chat.title,
                external_source="demo",
                metadata={"demo": True},
            )
            await uow.commit()
            for line in _DEMO_LINES:
                await IngestTranscriptEvent(
                    uow,
                    container.extractor,
                    container.telegram_gateway,
                    container.event_publisher,
                    container.config,
                ).execute(
                    TranscriptEvent(
                        meeting_id=meeting.public_id,
                        text=line,
                        ts=container.config.now(),
                        source=TranscriptSource.demo,
                    )
                )
            return _text(
                chat_id,
                f"Демо-сценарий запущен.\nСоздана встреча {meeting.public_id}.\n"
                "Я отправил несколько реплик как transcript events.",
            )
        if command == "demo_transcript":
            active_meeting = await uow.meetings.get_active_for_chat(chat_id)
            if active_meeting is None:
                return _text(chat_id, "Сначала запусти /meeting_start или /demo_start.")
            await IngestTranscriptEvent(
                uow,
                container.extractor,
                container.telegram_gateway,
                container.event_publisher,
                container.config,
            ).execute(
                TranscriptEvent(
                    meeting_id=active_meeting.public_id,
                    text=_DEMO_LINES[0],
                    ts=container.config.now(),
                    source=TranscriptSource.demo,
                )
            )
            return _text(
                chat_id,
                f"Тестовая реплика добавлена во встречу {active_meeting.public_id}.",
            )
        if command == "demo_reset":
            if container.settings.app_env != "dev":
                return _text(chat_id, "Demo reset доступен только в dev-режиме.")
            result = await uow.debug.reset_demo()
            await uow.commit()
            return _text(
                chat_id,
                f"Демо-данные очищены. Встреч: {result['meetings']}, "
                f"реплик: {result['transcripts']}.",
            )

    if command == "start":
        return _text(chat_id, _START_TEXT)
    if command == "help":
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


def _text(chat_id: int, text: str) -> ActionsResponse:
    return ActionsResponse(actions=[SendMessageAction(chat_id=chat_id, text=text)])
