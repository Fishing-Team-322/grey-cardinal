"""Internal endpoints для telegram-bot: message / callback / command.

UX: все взаимодействия через inline-кнопки. Команды только для продвинутых
пользователей — простой пользователь просто нажимает кнопки.
"""

from __future__ import annotations

import logging
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
from brain_api.application.use_cases.send_personal_evening_digests import (
    SendPersonalEveningDigests,
)
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

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/internal/telegram",
    tags=["internal-telegram"],
    dependencies=[Depends(verify_internal_token)],
)

# ── Callback action prefixes ─────────────────────────────────────────────────
CB_MENU_MAIN       = "menu:main"
CB_MENU_TASKS      = "menu:tasks"
CB_MENU_MEETINGS   = "menu:meetings"
CB_MENU_SETTINGS   = "menu:settings"
CB_MENU_DIGEST     = "menu:digest"
CB_SETUP_JIRA      = "setup:jira"
CB_SETUP_YOUGILE   = "setup:yougile"
CB_MEETING_START   = "meeting:start"
CB_MEETING_STOP    = "meeting:stop"
CB_MEETING_STATUS  = "meeting:status"
CB_TASK_LIST       = "task:list"
CB_DEMO_RUN        = "demo:run"
CB_BIND_CHAT       = "chat:bind"

_DEMO_LINES = [
    "Петя, подготовь оплату до завтра 18:00",
    "Аня, проверь интеграцию с Jira сегодня вечером",
    "Дима, подними websocket для дашборда до завтра",
]

# ── Inline keyboard builders ─────────────────────────────────────────────────

def _kb(*rows: list[tuple[str, str]]) -> dict:
    """Build inline_keyboard reply_markup from rows of (text, callback_data)."""
    return {
        "inline_keyboard": [
            [{"text": t, "callback_data": d} for t, d in row]
            for row in rows
        ]
    }


def _main_menu_kb(is_group: bool = False) -> dict:
    if is_group:
        return _kb(
            [("📋 Задачи команды", CB_TASK_LIST), ("🎙 Встречи", CB_MENU_MEETINGS)],
            [("📊 Дайджест", CB_MENU_DIGEST), ("⚙️ Настройки", CB_MENU_SETTINGS)],
            [("🚀 Запустить демо", CB_DEMO_RUN)],
        )
    return _kb(
        [("📋 Мои задачи", CB_TASK_LIST), ("📊 Дайджест", CB_MENU_DIGEST)],
        [("🎙 Встречи", CB_MENU_MEETINGS), ("⚙️ Настройки", CB_MENU_SETTINGS)],
        [("🚀 Запустить демо", CB_DEMO_RUN)],
    )


def _meetings_kb() -> dict:
    return _kb(
        [("▶️ Начать встречу", CB_MEETING_START), ("⏹ Завершить", CB_MEETING_STOP)],
        [("📊 Статус встречи", CB_MEETING_STATUS)],
        [("↩️ Главное меню", CB_MENU_MAIN)],
    )


def _settings_kb() -> dict:
    return _kb(
        [("🔵 Подключить Jira", CB_SETUP_JIRA), ("🟡 Подключить YouGile", CB_SETUP_YOUGILE)],
        [("📌 Привязать чат", CB_BIND_CHAT)],
        [("↩️ Главное меню", CB_MENU_MAIN)],
    )


def _back_kb() -> dict:
    return _kb([("↩️ Главное меню", CB_MENU_MAIN)])


# ── Welcome texts ─────────────────────────────────────────────────────────────

_WELCOME_PRIVATE = (
    "🤖 *Серый Кардинал* — ваш автономный PM-агент\n\n"
    "Я слежу за перепиской в командных чатах, распознаю задачи "
    "из сообщений и голосовых, создаю карточки в Jira и напоминаю о дедлайнах — "
    "всё в фоне, без ручного ввода.\n\n"
    "Выберите действие:"
)

_WELCOME_GROUP = (
    "🤖 *Серый Кардинал* подключён к чату!\n\n"
    "Начинаю автономный мониторинг:\n"
    "✅ Слежу за сообщениями и извлекаю задачи\n"
    "✅ Обрабатываю голосовые сообщения\n"
    "✅ Создаю карточки в Jira автоматически\n"
    "✅ Напоминаю о дедлайнах\n\n"
    "Первым делом подключите Jira или запустите демо:"
)

_HELP_TEXT = (
    "📖 *Серый Кардинал* — команды\n\n"
    "Большинство действий — через кнопки. Дополнительные команды:\n\n"
    "`/jira URL EMAIL TOKEN ПРОЕКТ` — подключить Jira\n"
    "  Пример: `/jira https://team.atlassian.net user@mail.com token123 PROJ`\n\n"
    "`/done GC\\-1` — закрыть задачу\n"
    "`/start_task GC\\-1` — взять в работу\n"
    "`/block GC\\-1` — заблокировать\n"
    "`/digest` — вечерний дайджест"
)

_JIRA_SETUP_TEXT = (
    "🔵 *Подключение Jira*\n\n"
    "Отправь команду в формате:\n"
    "`/jira URL EMAIL API\\_TOKEN ПРОЕКТ`\n\n"
    "Пример:\n"
    "`/jira https://myteam.atlassian.net user@mail.com token123 PROJ`\n\n"
    "API-токен создаётся на:\n"
    "id.atlassian.com → Security → API tokens"
)

_YOUGILE_SETUP_TEXT = (
    "🟡 *Подключение YouGile*\n\n"
    "Задайте переменные окружения на сервере:\n"
    "`BOARD_PROVIDER=yougile`\n"
    "`YOUGILE_API_KEY=...`\n"
    "`YOUGILE_PROJECT_ID=...`\n"
    "`YOUGILE_COLUMN_TODO_ID=...`\n\n"
    "После настройки перезапустите бота."
)


# ── Routes ────────────────────────────────────────────────────────────────────

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
    data = event.data
    chat_id = event.message.chat_id
    msg_id = event.message.message_id
    cq_id = event.callback_query_id

    # ── Navigation callbacks ──────────────────────────────────────────────
    if data == CB_MENU_MAIN:
        return _edit_with_kb(chat_id, msg_id, cq_id, _WELCOME_PRIVATE, _main_menu_kb())

    if data == CB_MENU_SETTINGS:
        return _edit_with_kb(chat_id, msg_id, cq_id, "⚙️ *Настройки интеграций*\n\nВыберите доску:", _settings_kb())

    if data == CB_MENU_MEETINGS:
        return _edit_with_kb(chat_id, msg_id, cq_id, "🎙 *Управление встречами*", _meetings_kb())

    if data == CB_SETUP_JIRA:
        return _edit_with_kb(chat_id, msg_id, cq_id, _JIRA_SETUP_TEXT, _back_kb())

    if data == CB_SETUP_YOUGILE:
        return _edit_with_kb(chat_id, msg_id, cq_id, _YOUGILE_SETUP_TEXT, _back_kb())

    if data == CB_BIND_CHAT:
        async with container.make_uow() as uow:
            project = await uow.projects.ensure_default(container.config.default_workspace_name)
            await uow.chats.upsert(chat_id, "group", None, project.id)
            await uow.projects.set_default_chat(project.id, (await uow.chats.get_by_telegram_id(chat_id)).id)
            await uow.commit()
        return _edit_with_kb(
            chat_id, msg_id, cq_id,
            "✅ Чат привязан к workspace!\nТеперь я буду следить за сообщениями здесь.",
            _back_kb(),
        )

    # ── Meetings ─────────────────────────────────────────────────────────
    if data == CB_MEETING_START:
        async with container.make_uow() as uow:
            meeting = await start_meeting(
                uow, container.config,
                telegram_chat_id=chat_id, chat_type="group",
                chat_title=None, external_source="telegram",
            )
            await uow.commit()
        return _edit_with_kb(
            chat_id, msg_id, cq_id,
            f"▶️ *Встреча начата*\nID: `{meeting.public_id}`\nЯ слушаю — отправляй голосовые или пиши.",
            _meetings_kb(),
        )

    if data == CB_MEETING_STOP:
        async with container.make_uow() as uow:
            active = await uow.meetings.get_active_for_chat(chat_id)
            if active is None:
                return _answer(cq_id, "Нет активной встречи")
            active = await stop_meeting(uow, container.config, active)
            await uow.commit()
            dto = await meeting_response(uow, active)
        return _edit_with_kb(
            chat_id, msg_id, cq_id,
            f"⏹ *Встреча завершена* `{active.public_id}`\n"
            f"📝 Реплик: {dto.transcript_count}\n"
            f"✅ Задач извлечено: {dto.proposal_count}",
            _main_menu_kb(is_group=True),
        )

    if data == CB_MEETING_STATUS:
        async with container.make_uow() as uow:
            active = await uow.meetings.get_active_for_chat(chat_id)
            if active is None:
                return _answer(cq_id, "Нет активной встречи")
            dto = await meeting_response(uow, active)
        return _edit_with_kb(
            chat_id, msg_id, cq_id,
            f"📊 *Активная встреча*\nID: `{active.public_id}`\n"
            f"Начало: {active.started_at:%H:%M}\n"
            f"Реплик: {dto.transcript_count}\n"
            f"Задач: {dto.proposal_count}",
            _meetings_kb(),
        )

    # ── Tasks ─────────────────────────────────────────────────────────────
    if data == CB_TASK_LIST:
        async with container.make_uow() as uow:
            result = await ListTasks(uow, container.config).execute(chat_id)
        return _answer_and_edit(cq_id, chat_id, msg_id, result)

    # ── Digest ────────────────────────────────────────────────────────────
    if data == CB_MENU_DIGEST:
        async with container.make_uow() as uow:
            result = await SendPersonalEveningDigests(
                uow, container.telegram_gateway, container.config
            ).as_actions_for_user(event.from_user.id, chat_id)
        return _answer_and_add(cq_id, result)

    # ── Demo ──────────────────────────────────────────────────────────────
    if data == CB_DEMO_RUN:
        async with container.make_uow() as uow:
            meeting = await start_meeting(
                uow, container.config,
                telegram_chat_id=chat_id, chat_type="group",
                chat_title="Demo", external_source="demo",
                metadata={"demo": True},
            )
            await uow.commit()
            for line in _DEMO_LINES:
                await IngestTranscriptEvent(
                    uow, container.extractor, container.telegram_gateway,
                    container.event_publisher, container.config,
                ).execute(TranscriptEvent(
                    meeting_id=meeting.public_id,
                    text=line,
                    ts=container.config.now(),
                    source=TranscriptSource.demo,
                ))
        return _edit_with_kb(
            chat_id, msg_id, cq_id,
            f"🚀 *Демо запущено!*\nВстреча `{meeting.public_id}`\n\n"
            "Я отправил 3 тестовые реплики как transcript events.\n"
            "Предложения задач появятся выше ☝️",
            _main_menu_kb(is_group=True),
        )

    # ── Task proposal actions (confirm/reject) ────────────────────────────
    action, target_id = _parse_callback(data)

    if action == CB_EDIT:
        return ActionsResponse(actions=[
            AnswerCallbackAction(callback_query_id=cq_id, text=EDIT_STUB_TEXT, show_alert=True)
        ])

    if target_id is None:
        return _answer(cq_id, "Неизвестное действие")

    async with container.make_uow() as uow:
        if action == CB_CONFIRM:
            return await ConfirmTask(
                uow, container.board, container.event_publisher, container.config
            ).execute(
                confirmation_id=target_id,
                callback_query_id=cq_id,
                chat_id=chat_id,
                message_id=msg_id,
                actor_telegram_id=event.from_user.id,
            )
        if action == CB_REJECT:
            return await RejectTask(uow, container.event_publisher).execute(
                confirmation_id=target_id,
                callback_query_id=cq_id,
                chat_id=chat_id,
                message_id=msg_id,
                actor_telegram_id=event.from_user.id,
            )

    return _answer(cq_id, "Неизвестное действие")


@router.post("/command", response_model=ActionsResponse)
async def ingest_command(
    event: TelegramCommandEvent,
    container: Container = Depends(get_container),
) -> ActionsResponse:
    command = event.command.lower()
    chat_id = event.chat.id
    is_group = event.chat.type in ("group", "supergroup")

    # ── /start — главное меню с кнопками ─────────────────────────────────
    if command == "start":
        # Auto-bind group chat on /start
        if is_group:
            async with container.make_uow() as uow:
                project = await uow.projects.ensure_default(container.config.default_workspace_name)
                await uow.chats.upsert(chat_id, event.chat.type, event.chat.title, project.id)
                await uow.projects.set_default_chat(
                    project.id, (await uow.chats.get_by_telegram_id(chat_id)).id
                )
                await uow.commit()
            return ActionsResponse(actions=[SendMessageAction(
                chat_id=chat_id,
                text=_WELCOME_GROUP,
                parse_mode="Markdown",
                reply_markup=_main_menu_kb(is_group=True),
            )])
        return ActionsResponse(actions=[SendMessageAction(
            chat_id=chat_id,
            text=_WELCOME_PRIVATE,
            parse_mode="Markdown",
            reply_markup=_main_menu_kb(is_group=False),
        )])

    if command == "help":
        return ActionsResponse(actions=[SendMessageAction(
            chat_id=chat_id,
            text=_HELP_TEXT,
            parse_mode="MarkdownV2",
            reply_markup=_back_kb(),
        )])

    # ── /jira URL EMAIL TOKEN PROJECT ────────────────────────────────────
    if command == "jira":
        args = event.args
        if len(args) < 4:
            return _md(chat_id, _JIRA_SETUP_TEXT, _back_kb())
        jira_url, email, token, project = args[0], args[1], args[2], args[3]
        # Store in env (runtime — in-memory for demo; persistent via .env in prod)
        import os
        os.environ["JIRA_URL"] = jira_url
        os.environ["JIRA_EMAIL"] = email
        os.environ["JIRA_API_TOKEN"] = token
        os.environ["JIRA_PROJECT_KEY"] = project
        os.environ["BOARD_PROVIDER"] = "jira"
        return _md(
            chat_id,
            f"✅ *Jira подключена!*\n\n"
            f"URL: `{jira_url}`\n"
            f"Проект: `{project}`\n\n"
            "Теперь задачи из переписки будут создаваться в Jira автоматически.",
            _main_menu_kb(is_group),
        )

    # ── /digest ───────────────────────────────────────────────────────────
    if command == "digest":
        async with container.make_uow() as uow:
            if event.chat.type == "private":
                return await SendPersonalEveningDigests(
                    uow, container.telegram_gateway, container.config
                ).as_actions_for_user(event.sender.id, chat_id)
            actions = await SendEveningDigest(
                uow, container.telegram_gateway, container.config
            ).as_actions(chat_id)
            return actions

    # ── /tasks ────────────────────────────────────────────────────────────
    if command == "tasks":
        async with container.make_uow() as uow:
            return await ListTasks(uow, container.config).execute(chat_id)

    if command == "tasks_all":
        async with container.make_uow() as uow:
            tasks = await ListTasks(uow, container.config).list_active()
            from brain_api.application.rendering import render_task_list
            return ActionsResponse(actions=[SendMessageAction(
                chat_id=chat_id,
                text=render_task_list(tasks, container.config.timezone),
            )])

    # ── Task status commands ──────────────────────────────────────────────
    _STATUS_COMMANDS = {"start_task", "block", "done"}
    if command in _STATUS_COMMANDS:
        async with container.make_uow() as uow:
            return await UpdateTaskStatus(
                uow, container.board, container.event_publisher, container.config
            ).execute(command, event.args, chat_id)

    # ── Meeting commands ──────────────────────────────────────────────────
    if command == "meeting_start":
        async with container.make_uow() as uow:
            meeting = await start_meeting(
                uow, container.config,
                telegram_chat_id=chat_id, chat_type=event.chat.type,
                chat_title=event.chat.title, external_source="telegram",
            )
            await uow.commit()
        return _md(chat_id, f"▶️ *Встреча начата*: `{meeting.public_id}`", _meetings_kb())

    if command == "meeting_stop":
        async with container.make_uow() as uow:
            active = await uow.meetings.get_active_for_chat(chat_id)
            if active is None:
                return _text(chat_id, "Нет активной встречи.")
            active = await stop_meeting(uow, container.config, active)
            await uow.commit()
            dto = await meeting_response(uow, active)
        return _md(chat_id,
            f"⏹ *Встреча завершена* `{active.public_id}`\n"
            f"Реплик: {dto.transcript_count} | Задач: {dto.proposal_count}",
            _meetings_kb())

    if command == "meeting_status":
        async with container.make_uow() as uow:
            active = await uow.meetings.get_active_for_chat(chat_id)
            if active is None:
                return _text(chat_id, "Нет активной встречи.")
            dto = await meeting_response(uow, active)
        return _md(chat_id,
            f"📊 *Встреча* `{active.public_id}`\nСтарт: {active.started_at:%H:%M}\n"
            f"Реплик: {dto.transcript_count} | Задач: {dto.proposal_count}",
            _meetings_kb())

    # ── Demo commands ─────────────────────────────────────────────────────
    if command == "demo_start":
        async with container.make_uow() as uow:
            meeting = await start_meeting(
                uow, container.config,
                telegram_chat_id=chat_id, chat_type=event.chat.type,
                chat_title=event.chat.title, external_source="demo",
                metadata={"demo": True},
            )
            await uow.commit()
            for line in _DEMO_LINES:
                await IngestTranscriptEvent(
                    uow, container.extractor, container.telegram_gateway,
                    container.event_publisher, container.config,
                ).execute(TranscriptEvent(
                    meeting_id=meeting.public_id, text=line,
                    ts=container.config.now(), source=TranscriptSource.demo,
                ))
        return _text(chat_id,
            f"🚀 Демо запущено. Встреча {meeting.public_id}. "
            "Предложения задач появятся выше.")

    if command == "demo_reset":
        if container.settings.app_env != "dev":
            return _text(chat_id, "Demo reset доступен только в dev.")
        async with container.make_uow() as uow:
            result = await uow.debug.reset_demo()
            await uow.commit()
        return _text(chat_id, f"Очищено: встреч {result['meetings']}, реплик {result['transcripts']}.")

    if command == "bind_chat":
        async with container.make_uow() as uow:
            project = await uow.projects.ensure_default(container.config.default_workspace_name)
            await uow.chats.upsert(chat_id, event.chat.type, event.chat.title, project.id)
            await uow.projects.set_default_chat(
                project.id, (await uow.chats.get_by_telegram_id(chat_id)).id
            )
            await uow.commit()
        return _text(chat_id, f"✅ Чат привязан к workspace: {project.name}")

    return ActionsResponse(actions=[SendMessageAction(
        chat_id=chat_id,
        text=f"Неизвестная команда /{command}. Нажми /start для меню.",
    )])


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _md(chat_id: int, text: str, kb: dict | None = None) -> ActionsResponse:
    return ActionsResponse(actions=[SendMessageAction(
        chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=kb,
    )])


def _answer(cq_id: str, text: str) -> ActionsResponse:
    return ActionsResponse(actions=[AnswerCallbackAction(callback_query_id=cq_id, text=text)])


def _edit_with_kb(chat_id: int, msg_id: int, cq_id: str, text: str, kb: dict) -> ActionsResponse:
    from grey_cardinal_contracts import EditMessageAction
    return ActionsResponse(actions=[
        AnswerCallbackAction(callback_query_id=cq_id, text=""),
        EditMessageAction(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=kb, parse_mode="Markdown"),
    ])


def _answer_and_edit(cq_id: str, chat_id: int, msg_id: int, result: ActionsResponse) -> ActionsResponse:
    return ActionsResponse(actions=[
        AnswerCallbackAction(callback_query_id=cq_id, text=""),
        *result.actions,
    ])


def _answer_and_add(cq_id: str, result: ActionsResponse) -> ActionsResponse:
    return ActionsResponse(actions=[
        AnswerCallbackAction(callback_query_id=cq_id, text=""),
        *result.actions,
    ])
