"""Internal endpoints для telegram-bot: message / callback / command.

UX: все взаимодействия через inline-кнопки. Команды только для продвинутых
пользователей — простой пользователь просто нажимает кнопки.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, tzinfo
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.application.agentic_tasks import (
    AssigneeCandidate,
    AssigneeResolution,
    IdentityResolver,
    InteractionMode,
    TaskDecisionEngine,
)
from brain_api.application.rendering import (
    CB_CONFIRM,
    CB_EDIT,
    CB_REJECT,
    EDIT_STUB_TEXT,
    format_deadline,
    proposal_keyboard,
)
from brain_api.application.semantic_parser import SemanticMessageInput
from brain_api.application.task_status_service import TaskStatusService
from brain_api.application.telemost_intent import detect_call_intent
from brain_api.application.use_cases import yandex_telemost as telemost_svc
from brain_api.application.use_cases.confirm_task import ConfirmTask
from brain_api.application.use_cases.ingest_chat_message import IngestChatMessage
from brain_api.application.use_cases.ingest_transcript_event import IngestTranscriptEvent
from brain_api.application.use_cases.list_tasks import ListTasks
from brain_api.application.use_cases.manage_meetings import (
    meeting_response,
    start_meeting,
    stop_meeting,
)
from brain_api.application.use_cases.meeting_flow import (
    CB_MTG_NO,
    CB_MTG_OK,
    _parse_time_to_dt,
    build_meeting_proposal,
    handle_meeting_callback,
    handle_pending_meeting_time,
    is_meeting_callback,
    rsvp_keyboard,
)
from brain_api.application.use_cases.member_reports import (
    manager_report_from_membership,
    manager_report_menu,
    render_member_report,
)
from brain_api.application.use_cases.reject_task import RejectTask
from brain_api.application.use_cases.send_evening_digest import SendEveningDigest
from brain_api.application.use_cases.send_personal_evening_digests import (
    SendPersonalEveningDigests,
)
from brain_api.application.use_cases.task_help import (
    handle_help_callback,
    is_help_callback,
    is_help_request_text,
    materials_for_arg,
)
from brain_api.application.use_cases.task_status_flow import (
    handle_task_status_callback,
    is_task_status_callback,
)
from brain_api.application.use_cases.team_gamification import (
    ACHIEVEMENTS,
    TASK_COMPLETED_XP,
    grant_team_xp,
    team_leaderboard_text_for_chat,
)
from brain_api.application.use_cases.team_settings import (
    addressed_message_text,
    handle_settings_callback,
    is_settings_callback,
    open_settings,
    require_cardinal_mention,
)
from brain_api.config import get_settings
from brain_api.container import Container
from brain_api.domain.enums import TaskStatus
from brain_api.domain.services import format_public_id, parse_public_id, status_for_command
from brain_api.infrastructure.db import models as m
from brain_api.integrations.yandex_telemost import YandexTelemostError
from grey_cardinal_contracts import (
    ActionsResponse,
    AnswerCallbackAction,
    EditMessageAction,
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
CB_MENU_MAIN = "menu:main"
CB_MENU_TASKS = "menu:tasks"
CB_MENU_MEETINGS = "menu:meetings"
CB_MENU_SETTINGS = "menu:settings"
CB_MENU_DIGEST = "menu:digest"
CB_MENU_LEADERBOARD = "menu:leaderboard"
CB_MENU_REPORTS = "menu:reports"
CB_SETUP_JIRA = "setup:jira"
CB_SETUP_YOUGILE = "setup:yougile"
CB_MEETING_START = "meeting:start"
CB_MEETING_STOP = "meeting:stop"
CB_MEETING_STATUS = "meeting:status"
CB_TASK_LIST = "task:list"
CB_DEMO_RUN = "demo:run"
CB_BIND_CHAT = "chat:bind"
CB_MODE_CONFIRM = "mode:confirm"
CB_MODE_AUTO = "mode:auto"
CB_TELEMOST_CREATE = "tmcall:create"
CB_TELEMOST_DISMISS = "tmcall:dismiss"

_DEMO_LINES = [
    "Петя, подготовь оплату до завтра 18:00",
    "Аня, проверь интеграцию с Jira сегодня вечером",
    "Дима, подними websocket для дашборда до завтра",
]

# ── Inline keyboard builders ─────────────────────────────────────────────────


def _kb(*rows: list[tuple[str, str]]) -> dict:
    """Build inline_keyboard reply_markup from rows of (text, callback_data)."""
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


def _telemost_prompt_kb() -> dict:
    return _kb(
        [("📹 Создать ссылку на созвон", CB_TELEMOST_CREATE)],
        [("Не сейчас", CB_TELEMOST_DISMISS)],
    )


def _main_menu_kb(is_group: bool = False) -> dict:
    if is_group:
        return _kb(
            [("📋 Задачи команды", CB_TASK_LIST), ("🎙 Встречи", CB_MENU_MEETINGS)],
            [("🏆 Лидерборд", CB_MENU_LEADERBOARD), ("📊 Дайджест", CB_MENU_DIGEST)],
            [("📈 Отчёты по сотрудникам", CB_MENU_REPORTS)],
            [("⚙️ Настройки", CB_MENU_SETTINGS)],
        )
    kb = _kb(
        [("📋 Мои задачи", CB_TASK_LIST), ("📊 Дайджест", CB_MENU_DIGEST)],
        [("🎙 Встречи", CB_MENU_MEETINGS), ("🏆 Лидерборд", CB_MENU_LEADERBOARD)],
        [("📈 Отчёты по сотрудникам", CB_MENU_REPORTS)],
        [("⚙️ Настройки", CB_MENU_SETTINGS)],
    )
    app_url = _tgapp_url()
    if app_url:
        kb["inline_keyboard"].insert(
            0, [{"text": "📱 Открыть приложение", "web_app": {"url": app_url}}]
        )
    return kb


def _tgapp_url() -> str:
    base = (
        get_settings().telegram_public_base_url
        or get_settings().public_base_url
        or ""
    ).rstrip("/")
    return f"{base}/tgapp/" if base else ""


def _confirmation_mode_kb() -> dict:
    return _kb(
        [("С подтверждением", CB_MODE_CONFIRM), ("Без подтверждения", CB_MODE_AUTO)],
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
    "Я буду следить за сообщениями и голосовыми, находить задачи и создавать "
    "карточки в YouGile.\n\n"
    "Как создавать задачи?"
)

_HELP_TEXT = (
    "📖 <b>Серый Кардинал</b> — команды\n\n"
    "Большинство действий — через кнопки. Дополнительные команды:\n\n"
    "<code>/task @user что сделать до срока</code> — явно создать задачу\n"
    "<code>/howto тема</code> — материалы по теме\n"
    "<code>/done GC-1</code> — закрыть задачу\n"
    "<code>/start_task GC-1</code> — взять в работу\n"
    "<code>/block GC-1</code> — заблокировать\n"
    "<code>/digest</code> — вечерний дайджест\n"
    "<code>/leaderboard</code> — рейтинг команды\n"
    "<code>/reports</code> — отчёт по сотруднику для руководителя\n"
    "<code>/unlink</code> — отвязать Telegram-аккаунт"
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
    "Откройте настройки команды на сайте и войдите в YouGile. "
    "Ключ API будет получен и зашифрован автоматически."
)

_UNBOUND_TEAM_TEXT = (
    "Этот чат ещё не привязан к команде Grey Cardinal.\n"
    "Создайте bind-code в кабинете команды и выполните /bind_team CODE."
)


class TelegramLinkRequest(BaseModel):
    code: str
    tg_user_id: int
    chat_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class TelegramBindTeamRequest(BaseModel):
    code: str
    tg_chat_id: int
    chat_id: int
    chat_type: str = "group"
    title: str | None = None
    linked_by_tg_user_id: int | None = None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/link", response_model=ActionsResponse)
async def link_telegram_account(
    payload: TelegramLinkRequest,
    container: Container = Depends(get_container),
) -> ActionsResponse:
    now = datetime.now(UTC)
    code = payload.code.strip().upper()
    async with container.session_factory() as session:
        link = await session.scalar(
            select(m.TelegramLinkCodeModel).where(m.TelegramLinkCodeModel.code == code)
        )
        if link is None or link.used_at is not None:
            return _text(payload.chat_id, "Код привязки не найден или уже использован.")

        expires_at = link.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now:
            link.used_at = now
            await session.commit()
            return _text(payload.chat_id, "Код привязки истёк. Создай новый код на сайте.")

        user = await session.get(m.UserModel, link.user_id)
        if user is None:
            link.used_at = now
            await session.commit()
            return _text(payload.chat_id, "Аккаунт для этого кода не найден.")

        existing = await session.scalar(
            select(m.UserModel).where(m.UserModel.telegram_user_id == payload.tg_user_id)
        )
        if existing is not None and existing.id != user.id:
            return _text(payload.chat_id, "Этот Telegram уже привязан к другому аккаунту.")

        user.telegram_user_id = payload.tg_user_id
        user.telegram_username = payload.username
        if not user.display_name:
            user.display_name = _telegram_display_name(payload)
        link.used_at = now
        await session.commit()

    return _text(payload.chat_id, "✅ Telegram привязан к аккаунту Grey Cardinal.")


@router.post("/bind-team", response_model=ActionsResponse)
async def bind_team_chat(
    payload: TelegramBindTeamRequest,
    container: Container = Depends(get_container),
) -> ActionsResponse:
    now = datetime.now(UTC)
    code = payload.code.strip().upper()
    async with container.session_factory() as session:
        bind_code = await session.scalar(
            select(m.TelegramTeamBindCodeModel).where(m.TelegramTeamBindCodeModel.code == code)
        )
        if bind_code is None:
            return _text(payload.chat_id, "Код привязки команды не найден.")
        expires_at = bind_code.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now:
            return _text(payload.chat_id, "Код привязки чата истёк. Создай новый код.")
        if bind_code.used_at is not None:
            return _text(payload.chat_id, "Код привязки чата уже использован.")
        team = await session.get(m.TeamModel, bind_code.team_id)
        if team is None:
            return _text(payload.chat_id, "Команда для этого кода не найдена.")

        linker = None
        if payload.linked_by_tg_user_id is not None:
            linker = await session.scalar(
                select(m.UserModel).where(
                    m.UserModel.telegram_user_id == payload.linked_by_tg_user_id
                )
            )
        team.tg_chat_id = payload.tg_chat_id
        bind_code.used_at = now
        chat = await session.scalar(
            select(m.TelegramChatModel).where(
                m.TelegramChatModel.telegram_chat_id == payload.tg_chat_id
            )
        )
        if chat is None:
            chat = m.TelegramChatModel(
                team_id=team.id,
                telegram_chat_id=payload.tg_chat_id,
                type=payload.chat_type,
                title=payload.title,
                linked_by=linker.id if linker else None,
                linked_at=now,
            )
            session.add(chat)
        else:
            chat.team_id = team.id
            chat.type = payload.chat_type
            chat.title = payload.title
            chat.linked_by = linker.id if linker else chat.linked_by
            chat.linked_at = now
        session.add_all([team, bind_code])
        await session.commit()

    return _text(payload.chat_id, "✅ Чат привязан к команде Grey Cardinal.")


@router.post("/message", response_model=ActionsResponse)
async def ingest_message(
    event: TelegramMessageEvent,
    container: Container = Depends(get_container),
) -> ActionsResponse:
    # Личка: время созвона / «помощь по задаче» → материалы.
    if event.chat.type == "private":
        async with container.session_factory() as session:
            pending = await handle_pending_meeting_time(
                session, event.sender, event.text, datetime.now(UTC)
            )
            if pending is not None:
                return pending
            if is_help_request_text(event.text):
                return _html(event.chat.id, await materials_for_arg(session, event.text))

    semantic_text = event.text
    if event.chat.type in {"group", "supergroup", "channel"} and hasattr(
        container, "session_factory"
    ):
        async with container.session_factory() as session:
            team = await session.scalar(
                select(m.TeamModel).where(m.TeamModel.tg_chat_id == event.chat.id)
            )
        if team is not None:
            semantic_text = addressed_message_text(
                event.text,
                required=require_cardinal_mention(team),
            )
            if semantic_text is None:
                return await _try_v2_semantic_message(
                    event,
                    container,
                    ignore_reason="cardinal_mention_required",
                ) or ActionsResponse(actions=[])

    # Группа: явный intent «нужен созвон» → спросить про Телемост (не создаём сами).
    if (
        event.chat.type in {"group", "supergroup"}
        and semantic_text is not None
        and detect_call_intent(semantic_text)
    ):
        scheduled_response = await _try_scheduled_call_prompt(event, container, semantic_text)
        if scheduled_response is not None:
            return scheduled_response
        # If message had digits (attempted time) but we couldn't parse it → ask for clarification
        if re.search(r"\d", semantic_text or ""):
            return ActionsResponse(
                actions=[
                    SendMessageAction(
                        chat_id=event.chat.id,
                        text="🎙 Не понял время. Напиши, например: «созвон в 15:00» или «созвон в 18:30»",
                    )
                ]
            )
        # Autonomous mode: создаём комнату без вопроса (immediate, no time mentioned)
        if hasattr(container, "session_factory"):
            auto_room = await _try_autonomous_call_create(event, container)
            if auto_room is not None:
                return auto_room
        return ActionsResponse(
            actions=[
                SendMessageAction(
                    chat_id=event.chat.id,
                    text=(
                        "🎙 Похоже, нужен созвон. Создать ссылку на встречу?"
                    ),
                    reply_markup=_telemost_prompt_kb(),
                )
            ]
        )

    v2_response = await _try_v2_semantic_message(
        event,
        container,
        semantic_text=semantic_text,
    )
    if v2_response is not None:
        return v2_response

    async with container.make_uow() as uow:
        use_case = IngestChatMessage(
            uow,
            container.extractor,
            container.event_publisher,
            container.config,
            container.board,
        )
        return await use_case.execute(event)


async def _try_scheduled_call_prompt(
    event: TelegramMessageEvent,
    container: Container,
    semantic_text: str,
) -> ActionsResponse | None:
    if not hasattr(container, "session_factory"):
        return None

    async with container.session_factory() as session:
        team = await session.scalar(
            select(m.TeamModel).where(m.TeamModel.tg_chat_id == event.chat.id)
        )
        if team is None:
            return None

        now = datetime.now(UTC)
        scheduled_at = _parse_time_to_dt(semantic_text, now, team.timezone)
        if scheduled_at is None:
            return None

        sender = await session.scalar(
            select(m.UserModel).where(m.UserModel.telegram_user_id == event.sender.id)
        )
        if sender is None:
            sender = m.UserModel(
                telegram_user_id=event.sender.id,
                telegram_username=event.sender.username,
                display_name=_display_name_from_event(event),
            )
            session.add(sender)
            await session.flush()

        is_autonomous = bool((team.board_config or {}).get("autonomous_mode"))
        seq = int(await session.scalar(select(func.max(m.MeetingModel.seq))) or 0) + 1
        meeting = m.MeetingModel(
            seq=seq,
            public_id=f"MTG-{seq}",
            team_id=team.id,
            title="Созвон",
            status="scheduled" if is_autonomous else "proposed",
            state="scheduled" if is_autonomous else "proposed",
            created_by=sender.id,
            scheduled_at=scheduled_at,
            scheduled_timezone=team.timezone,
            duration_minutes=60,
            started_at=scheduled_at,
            metadata_json={
                "source": "telegram_call_intent",
                "raw_text": event.text,
                "semantic_text": semantic_text,
            },
        )
        session.add(meeting)
        await session.flush()
        meeting_id = meeting.id
        team_timezone = team.timezone
        await session.commit()

    when = format_deadline(scheduled_at, team_timezone)

    if is_autonomous:
        return ActionsResponse(
            actions=[
                SendMessageAction(
                    chat_id=event.chat.id,
                    text=f"✅ Созвон запланирован на {when}.\n\nКто придёт?",
                    reply_markup=rsvp_keyboard(meeting_id),
                )
            ]
        )

    return ActionsResponse(
        actions=[
            SendMessageAction(
                chat_id=event.chat.id,
                text=(
                    "🎙 Похоже, нужно запланировать созвон.\n\n"
                    f"Когда: {when}\n\n"
                    "Запланировать?"
                ),
                reply_markup=_kb(
                    [("✅ Да, запланировать", f"{CB_MTG_OK}:{meeting_id}")],
                    [("❌ Нет", f"{CB_MTG_NO}:{meeting_id}")],
                ),
            )
        ]
    )


async def _try_autonomous_call_create(
    event: TelegramMessageEvent,
    container: Container,
) -> ActionsResponse | None:
    """Если включён автономный режим — создать комнату созвона без подтверждения."""
    async with container.session_factory() as session:
        team = await session.scalar(
            select(m.TeamModel).where(m.TeamModel.tg_chat_id == event.chat.id)
        )
        if team is None or not (team.board_config or {}).get("autonomous_mode"):
            return None

        settings = get_settings()
        provider_label = "Яндекс Телемост"
        result: dict | None = None

        integration = await telemost_svc.get_integration(session, team.id)
        if integration is not None and integration.status == "connected":
            try:
                result = await telemost_svc.create_room_for_chat(
                    session,
                    settings,
                    telegram_chat_id=event.chat.id,
                    created_by_telegram_user_id=event.sender.id,
                )
            except (telemost_svc.TelemostNotConnected, YandexTelemostError) as exc:
                logger.warning("[telemost] autonomous room creation failed, using Jitsi: %s", exc)
                await session.rollback()
                result = None

        if result is None or not result.get("join_url"):
            result = await telemost_svc.create_jitsi_room_for_chat(
                session,
                telegram_chat_id=event.chat.id,
                created_by_telegram_user_id=event.sender.id,
            )
            provider_label = "Видеовстреча (Jitsi)"

        await session.commit()

    join_url = result.get("join_url") if result else None
    if not join_url:
        return None

    return ActionsResponse(
        actions=[
            SendMessageAction(
                chat_id=event.chat.id,
                text=f"🎙 {provider_label}\n\n🔗 {join_url}",
            )
        ]
    )


@router.post("/callback", response_model=ActionsResponse)
async def ingest_callback(
    event: TelegramCallbackEvent,
    container: Container = Depends(get_container),
) -> ActionsResponse:
    data = event.data
    chat_id = event.message.chat_id
    msg_id = event.message.message_id
    cq_id = event.callback_query_id

    if data.startswith("taskcmd:"):
        return await _handle_taskcmd_callback(container, event)

    # ── Telemost: выбор провайдера для созвона ────────────────────────────
    if data.startswith("tmcall:"):
        return await _handle_telemost_callback(container, event)

    # ── Meeting (созвон) callbacks: подтверждение времени и RSVP ──────────
    if is_meeting_callback(data):
        async with container.session_factory() as session:
            return await handle_meeting_callback(session, data, event)

    # ── Task status callbacks (сценарий 3): В процессе / Сделал / Не буду ──
    if is_task_status_callback(data):
        return await handle_task_status_callback(container, data, event)

    # ── Материалы по задаче ──────────────────────────────────────────────
    if is_help_callback(data):
        async with container.session_factory() as session:
            return await handle_help_callback(session, data, event)

    # ── Меню настроек команды ────────────────────────────────────────────
    if is_settings_callback(data):
        async with container.session_factory() as session:
            return await handle_settings_callback(session, data, event)

    if data.startswith("report:member:"):
        try:
            membership_id = UUID(data.rsplit(":", 1)[-1])
        except ValueError:
            return _answer(cq_id, "Некорректный отчёт.")
        async with container.session_factory() as session:
            report = await manager_report_from_membership(
                session,
                telegram_user_id=event.from_user.id,
                membership_id=membership_id,
            )
        if report is None:
            return _answer(cq_id, "Отчёт доступен только руководителю этой команды.")
        return ActionsResponse(
            actions=[
                AnswerCallbackAction(callback_query_id=cq_id, text="Отчёт отправлен в личку."),
                SendMessageAction(
                    chat_id=event.from_user.id,
                    text=render_member_report(report),
                    reply_markup=_kb([("↩️ Другой сотрудник", CB_MENU_REPORTS)]),
                ),
            ]
        )

    # ── Navigation callbacks ──────────────────────────────────────────────
    if data == CB_MENU_MAIN:
        return _edit_with_kb(chat_id, msg_id, cq_id, _WELCOME_PRIVATE, _main_menu_kb())

    if data == CB_MENU_SETTINGS:
        return _edit_with_kb(
            chat_id,
            msg_id,
            cq_id,
            "⚙️ *Настройки интеграций*\n\nВыберите доску:",
            _settings_kb(),
        )

    if data == CB_MENU_LEADERBOARD:
        async with container.session_factory() as session:
            text = await team_leaderboard_text_for_chat(session, chat_id)
        return _edit_with_kb(chat_id, msg_id, cq_id, text, _back_kb())

    if data == CB_MENU_REPORTS:
        async with container.session_factory() as session:
            text, keyboard = await manager_report_menu(session, event.from_user.id)
        return ActionsResponse(
            actions=[
                AnswerCallbackAction(callback_query_id=cq_id, text="Открываю отчёты в личке."),
                SendMessageAction(
                    chat_id=event.from_user.id,
                    text=text,
                    reply_markup=keyboard,
                ),
            ]
        )

    if data in (CB_MODE_CONFIRM, CB_MODE_AUTO):
        required = data == CB_MODE_CONFIRM
        if not hasattr(container, "session_factory"):
            async with container.make_uow() as uow:
                project = await uow.projects.ensure_default(container.config.default_workspace_name)
                chat = await uow.chats.get_by_telegram_id(chat_id)
                if chat is None:
                    await uow.chats.upsert(chat_id, "supergroup", None, project.id)
                else:
                    await uow.chats.upsert(chat_id, chat.type, chat.title, project.id)
                await uow.chats.set_confirmation_required(chat_id, required)
                await uow.commit()
            mode_text = (
                "✅ Режим включён: задачи создаются после подтверждения в чате."
                if required
                else "✅ Режим включён: задачи создаются сразу, без сообщений в чат."
            )
            return _edit_with_kb(
                chat_id,
                msg_id,
                cq_id,
                f"{mode_text}\n\nЯ уже мониторю чат.",
                _main_menu_kb(is_group=True),
            )
        async with container.session_factory() as session:
            chat = await session.scalar(
                select(m.TelegramChatModel).where(m.TelegramChatModel.telegram_chat_id == chat_id)
            )
            if chat is None or chat.team_id is None:
                return _edit_with_kb(chat_id, msg_id, cq_id, _UNBOUND_TEAM_TEXT, _back_kb())
            chat.task_confirmation_required = required
            await session.commit()
        mode_text = (
            "✅ Режим включён: задачи создаются после подтверждения в чате."
            if required
            else "✅ Режим включён: задачи создаются сразу, без сообщений в чат."
        )
        return _edit_with_kb(
            chat_id,
            msg_id,
            cq_id,
            f"{mode_text}\n\nЯ уже мониторю чат.",
            _main_menu_kb(is_group=True),
        )

    if data == CB_MENU_MEETINGS:
        return _edit_with_kb(chat_id, msg_id, cq_id, "🎙 *Управление встречами*", _meetings_kb())

    if data == CB_SETUP_JIRA:
        return _edit_with_kb(chat_id, msg_id, cq_id, _JIRA_SETUP_TEXT, _back_kb())

    if data == CB_SETUP_YOUGILE:
        return _edit_with_kb(chat_id, msg_id, cq_id, _YOUGILE_SETUP_TEXT, _back_kb())

    if data == CB_BIND_CHAT:
        return _edit_with_kb(
            chat_id,
            msg_id,
            cq_id,
            _UNBOUND_TEAM_TEXT,
            _back_kb(),
        )

    # ── Meetings ─────────────────────────────────────────────────────────
    if data == CB_MEETING_START:
        async with container.make_uow() as uow:
            meeting = await start_meeting(
                uow,
                container.config,
                telegram_chat_id=chat_id,
                chat_type="group",
                chat_title=None,
                external_source="telegram",
            )
            await uow.commit()
        return _edit_with_kb(
            chat_id,
            msg_id,
            cq_id,
            f"▶️ *Встреча начата*\nID: `{meeting.public_id}`\n"
            "Я слушаю — отправляй голосовые или пиши.",
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
            chat_id,
            msg_id,
            cq_id,
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
            chat_id,
            msg_id,
            cq_id,
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
                uow,
                container.config,
                telegram_chat_id=chat_id,
                chat_type="group",
                chat_title="Demo",
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
        return _edit_with_kb(
            chat_id,
            msg_id,
            cq_id,
            f"🚀 *Демо запущено!*\nВстреча `{meeting.public_id}`\n\n"
            "Я отправил 3 тестовые реплики как transcript events.\n"
            "Предложения задач появятся выше ☝️",
            _main_menu_kb(is_group=True),
        )

    # ── Task proposal actions (confirm/reject) ────────────────────────────
    action, target_id = _parse_callback(data)

    if action == CB_EDIT:
        return ActionsResponse(
            actions=[
                AnswerCallbackAction(callback_query_id=cq_id, text=EDIT_STUB_TEXT, show_alert=True)
            ]
        )

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


async def _try_v2_semantic_message(
    event: TelegramMessageEvent | TelegramCommandEvent,
    container: Container,
    *,
    interaction_mode: InteractionMode = InteractionMode.AUTO_BACKGROUND,
    semantic_text: str | None = None,
    ignore_reason: str | None = None,
) -> ActionsResponse | None:
    if event.chat.type not in {"group", "supergroup", "channel"}:
        return None

    now = datetime.now(UTC)
    async with container.session_factory() as session:
        team = await session.scalar(
            select(m.TeamModel).where(m.TeamModel.tg_chat_id == event.chat.id)
        )
        if team is None:
            return _text(
                event.chat.id,
                "Этот чат ещё не привязан к команде Grey Cardinal. "
                "Менеджер команды должен привязать его в настройках команды.",
            )

        chat = await session.scalar(
            select(m.TelegramChatModel).where(m.TelegramChatModel.telegram_chat_id == event.chat.id)
        )
        if chat is None:
            chat = m.TelegramChatModel(
                team_id=team.id,
                telegram_chat_id=event.chat.id,
                type=event.chat.type,
                title=event.chat.title,
                linked_at=now,
            )
            session.add(chat)
            await session.flush()
        elif chat.team_id != team.id:
            chat.team_id = team.id

        sender = await session.scalar(
            select(m.UserModel).where(m.UserModel.telegram_user_id == event.sender.id)
        )
        if sender is None:
            sender = m.UserModel(
                telegram_user_id=event.sender.id,
                telegram_username=event.sender.username,
                display_name=_display_name_from_event(event),
            )
            session.add(sender)
            await session.flush()

        existing = await session.scalar(
            select(m.ChatMessageModel).where(
                m.ChatMessageModel.chat_id == chat.id,
                m.ChatMessageModel.telegram_message_id == event.message_id,
            )
        )
        if existing is not None:
            await session.commit()
            return ActionsResponse(actions=[])

        reply_sender = None
        if event.reply_to_sender is not None:
            reply_sender = await session.scalar(
                select(m.UserModel)
                .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
                .where(
                    m.TeamMemberModel.team_id == team.id,
                    m.UserModel.telegram_user_id == event.reply_to_sender.id,
                )
            )
        message = m.ChatMessageModel(
            telegram_message_id=event.message_id,
            chat_id=chat.id,
            sender_id=sender.id,
            sender_telegram_user_id=event.sender.id,
            reply_to_message_id=event.reply_to_message_id,
            reply_to_sender_user_id=reply_sender.id if reply_sender else None,
            reply_to_sender_telegram_user_id=(
                event.reply_to_sender.id if event.reply_to_sender else None
            ),
            reply_to_text=event.reply_to_text,
            message_thread_id=event.message_thread_id,
            text=event.text,
            raw_json=event.raw or {},
        )
        session.add(message)
        await session.flush()

        if ignore_reason is not None:
            session.add(
                m.AuditLogModel(
                    actor_type="system",
                    action="semantic_message_ignored",
                    entity_type="chat_message",
                    entity_id=message.id,
                    payload={"team_id": str(team.id), "reason": ignore_reason},
                )
            )
            await session.commit()
            return ActionsResponse(actions=[])

        member_names = list(
            await session.scalars(
                select(m.UserModel.display_name)
                .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
                .where(m.TeamMemberModel.team_id == team.id)
            )
        )

        try:
            parsed = await container.semantic_parser.parse(
                SemanticMessageInput(
                    team_id=team.id,
                    message_text=semantic_text or event.text,
                    sender_user_id=sender.id,
                    team_timezone=team.timezone,
                    now=now,
                    sender_display_name=sender.display_name,
                    team_members=member_names,
                    interaction_mode=interaction_mode.value,
                    reply_to_text=event.reply_to_text,
                    reply_to_sender_display_name=(
                        reply_sender.display_name if reply_sender else None
                    ),
                )
            )
        except Exception as exc:
            session.add(
                m.AuditLogModel(
                    actor_type="system",
                    action="semantic_parse_failed",
                    entity_type="chat_message",
                    entity_id=message.id,
                    payload={"team_id": str(team.id), "error": str(exc)},
                )
            )
            await session.commit()
            return ActionsResponse(actions=[])

        kind = parsed["kind"]
        confidence = float(parsed["confidence"])

        # ── Heuristic override: LLM often misclassifies "X сделал задачу Y"
        # as task_candidate instead of status_update.
        # Apply BEFORE routing so the correct handler runs.  ─────────────────
        if kind == "task_candidate":
            _heuristic_status = _detect_status_update_heuristic(semantic_text or event.text)
            if _heuristic_status is not None:
                _patched = dict(parsed)
                _patched["kind"] = "status_update"
                _patched["daily_report"] = {"detected_status": _heuristic_status, "summary": None}
                return await _route_v2_status_update(
                    session, container, team, sender, message, _patched, event
                )

        if kind == "task_candidate":
            resolver = IdentityResolver(session)
            task_payload = parsed.get("task") or {}
            resolution = await resolver.resolve_assignee(
                team.id,
                task_payload.get("assignee_reference") or task_payload.get("assignee_text"),
                event.entities,
                event.text,
                reply_sender.id if reply_sender else None,
                interaction_mode,
            )
            autonomous_mode = bool((team.board_config or {}).get("autonomous_mode"))
            return await _route_v2_task_candidate(
                session,
                team,
                sender,
                message,
                parsed,
                event,
                resolution,
                interaction_mode,
                semantic_text or event.text,
                autonomous=autonomous_mode,
            )
        if kind == "meeting_candidate" and confidence >= 0.6:
            return await _route_v2_meeting_candidate(session, team, sender, message, parsed, event)
        if kind == "daily_report":
            return await _route_v2_daily_report(session, team, sender, message, parsed, event)
        if kind == "absence_notice":
            return await _route_v2_absence(session, team, sender, message, parsed, event)
        if kind == "status_update":
            return await _route_v2_status_update(
                session, container, team, sender, message, parsed, event
            )
        if interaction_mode in {
            InteractionMode.EXPLICIT_TASK_COMMAND,
            InteractionMode.REPLY_TASK_COMMAND,
        }:
            await session.commit()
            return _text(
                event.chat.id,
                "Я понял команду создания задачи, но не вижу конкретного рабочего результата. "
                "Напиши, что именно нужно сделать.",
            )

        session.add(
            m.AuditLogModel(
                actor_type="system",
                action="semantic_message_ignored",
                entity_type="chat_message",
                entity_id=message.id,
                payload={"team_id": str(team.id), "kind": kind, "confidence": confidence},
            )
        )
        await session.commit()
        return ActionsResponse(actions=[])


async def _route_v2_task_candidate(
    session,
    team,
    sender,
    message,
    parsed,
    event,
    resolution: AssigneeResolution,
    interaction_mode: InteractionMode,
    semantic_text: str,
    *,
    autonomous: bool = False,
):
    task = parsed.get("task") or {}
    title = str(task.get("title") or semantic_text[:120]).strip()
    assignee_text = (
        resolution.display_name
        or resolution.raw_reference
        or task.get("assignee_reference")
        or task.get("assignee_text")
    )
    deadline = _parse_dt(task.get("deadline"), team.timezone)
    duplicate = await _find_v2_duplicate(session, team.id, title, resolution.user_id)
    decision = TaskDecisionEngine().decide(
        semantic_result=parsed,
        identity_resolution=resolution,
        interaction_mode=interaction_mode,
        has_context=bool(event.reply_to_text),
        duplicate=duplicate is not None,
    )
    if decision.action == "ignore":
        await session.commit()
        return ActionsResponse(actions=[])
    if decision.action == "create_ai_inbox_item":
        # Autonomous mode: fall through to auto-create when:
        # - assignee is unknown but task is clear (needs_assignee)
        # - task object looks vague only because user wrote "задачу" explicitly,
        #   but LLM extracted a real title of ≥2 words (needs_task_object)
        _auto_create_anyway = autonomous and decision.reason == "needs_assignee"
        if not _auto_create_anyway and autonomous and decision.reason == "needs_task_object":
            _auto_create_anyway = len(title.split()) >= 2
        if _auto_create_anyway:
            pass  # fall through to proposal/auto-create below
        else:
            session.add(
                m.AIInboxItemModel(
                    team_id=team.id,
                    source_message_id=message.id,
                    kind=decision.reason
                    if decision.reason
                    in {
                        "needs_assignee",
                        "needs_task_object",
                        "duplicate_suspected",
                        "low_confidence",
                    }
                    else "task_candidate_uncertain",
                    status="pending",
                    reason=decision.reason,
                    raw_text=semantic_text,
                    semantic_payload=parsed,
                    identity_payload=resolution.payload(),
                    duplicate_task_id=duplicate.id if duplicate else None,
                    confidence=decision.confidence,
                )
            )
            await session.commit()
            return ActionsResponse(actions=[])
    if decision.action == "ask_clarification":
        if decision.reason == "needs_assignee":
            if not autonomous:
                return await _create_assignee_draft(
                    session,
                    team,
                    message,
                    parsed,
                    semantic_text,
                    resolution,
                    event.chat.id,
                )
            # Autonomous mode: fall through to auto-create with text-only assignee
        else:
            await session.commit()
            return _text(
                event.chat.id,
                "Я понял намерение создать задачу, но не понял конкретный результат. "
                "Напиши, что именно нужно сделать.",
            )
    if decision.action == "duplicate_warning" and duplicate is not None:
        proposal = m.TaskProposalModel(
            team_id=team.id,
            source="telegram_chat",
            source_message_id=message.id,
            title=title,
            description=task.get("description"),
            assignee_text=assignee_text,
            assignee_id=resolution.user_id,
            deadline=deadline,
            deadline_timezone=team.timezone,
            priority=task.get("priority") or "medium",
            confidence=float(parsed["confidence"]),
            raw_text=semantic_text,
            extractor_payload={**parsed, "identity_resolution": resolution.payload()},
            similar_task_id=duplicate.id,
        )
        session.add(proposal)
        await session.flush()
        confirmation = m.ConfirmationModel(
            team_id=team.id,
            proposal_id=proposal.id,
            status="pending",
            telegram_chat_id=event.chat.id,
        )
        session.add(confirmation)
        await session.commit()
        return ActionsResponse(
            actions=[
                SendMessageAction(
                    chat_id=event.chat.id,
                    text=(
                        "Похоже, такая задача уже есть:\n\n"
                        f"{duplicate.public_id} {duplicate.title}\n\nЧто сделать?"
                    ),
                    reply_markup={
                        "inline_keyboard": [
                            [
                                {
                                    "text": "Связать",
                                    "callback_data": f"taskcmd:link:{confirmation.id}",
                                },
                                {
                                    "text": "Создать всё равно",
                                    "callback_data": f"taskcmd:create_anyway:{confirmation.id}",
                                },
                            ],
                            [
                                {
                                    "text": "Отмена",
                                    "callback_data": f"taskcmd:cancel:{confirmation.id}",
                                }
                            ],
                        ]
                    },
                )
            ]
        )

    proposal = m.TaskProposalModel(
        team_id=team.id,
        source="telegram_chat",
        source_message_id=message.id,
        title=title,
        description=task.get("description"),
        assignee_text=assignee_text,
        assignee_id=resolution.user_id,
        deadline=deadline,
        deadline_timezone=team.timezone,
        priority=task.get("priority") or "medium",
        confidence=float(parsed["confidence"]),
        raw_text=semantic_text,
        extractor_payload={**parsed, "identity_resolution": resolution.payload()},
    )
    session.add(proposal)
    await session.flush()

    if autonomous:
        # Don't create phantom assignees: only link resolved users to the task.
        unresolved_name: str | None = None
        actual_assignee_id = resolution.user_id
        actual_assignee_text = assignee_text
        if resolution.status in {"unresolved", "ambiguous"}:
            unresolved_name = assignee_text  # keep for notification warning
            actual_assignee_id = None
            actual_assignee_text = None

        next_seq = int(
            await session.scalar(
                select(func.max(m.TaskModel.seq)).where(m.TaskModel.team_id == team.id)
            ) or 0
        ) + 1
        auto_task = m.TaskModel(
            seq=next_seq,
            public_id=f"GC-{next_seq}",
            team_id=team.id,
            title=title,
            description=task.get("description"),
            assignee_id=actual_assignee_id,
            assignee_text=actual_assignee_text,
            deadline=deadline,
            deadline_timezone=team.timezone,
            priority=task.get("priority") or "medium",
            status="todo",
            source="telegram_chat",
            source_message_id=message.id,
            created_from_proposal_id=proposal.id,
        )
        session.add(auto_task)
        auto_task_public_id = f"GC-{next_seq}"  # capture before commit — SQLAlchemy expires on commit
        await session.commit()
        deadline_str = (
            f"\nДедлайн: {format_deadline(deadline, team.timezone)}" if deadline else ""
        )
        if unresolved_name:
            assignee_str = f"\n⚠️ «{unresolved_name}» не найден в команде — исполнитель не назначен"
        elif actual_assignee_text:
            assignee_str = f"\nИсполнитель: {actual_assignee_text}"
        else:
            assignee_str = ""
        return ActionsResponse(
            actions=[
                SendMessageAction(
                    chat_id=event.chat.id,
                    text=f"✅ {auto_task_public_id}: {title}{assignee_str}{deadline_str}",
                )
            ]
        )

    confirmation = m.ConfirmationModel(
        team_id=team.id,
        proposal_id=proposal.id,
        status="pending",
        telegram_chat_id=event.chat.id,
    )
    session.add(confirmation)
    await session.commit()
    return ActionsResponse(
        actions=[
            SendMessageAction(
                chat_id=event.chat.id,
                text=(
                    "🧠 Нашёл задачу\n\n"
                    f"Что сделать:\n{proposal.title}\n\n"
                    f"Исполнитель:\n{proposal.assignee_text or 'без исполнителя'}\n\n"
                    "Дедлайн:\n"
                    f"{proposal.deadline.isoformat() if proposal.deadline else 'не указан'} "
                    f"{team.timezone}\n\nСоздать карточку?"
                ),
                reply_markup=proposal_keyboard(confirmation.id),
            )
        ]
    )


async def _create_assignee_draft(
    session,
    team,
    message,
    parsed,
    semantic_text,
    resolution: AssigneeResolution,
    chat_id: int,
) -> ActionsResponse:
    task = parsed.get("task") or {}
    proposal = m.TaskProposalModel(
        team_id=team.id,
        source="telegram_chat",
        source_message_id=message.id,
        title=str(task.get("title") or semantic_text[:120]).strip(),
        description=task.get("description"),
        assignee_text=task.get("assignee_reference") or task.get("assignee_text"),
        deadline=_parse_dt(task.get("deadline"), team.timezone),
        deadline_timezone=team.timezone,
        priority=task.get("priority") or "medium",
        confidence=float(parsed["confidence"]),
        raw_text=semantic_text,
        extractor_payload={
            **parsed,
            "identity_resolution": resolution.payload(),
            "draft_kind": "task_command",
        },
    )
    session.add(proposal)
    await session.flush()
    confirmation = m.ConfirmationModel(
        team_id=team.id,
        proposal_id=proposal.id,
        status="pending",
        telegram_chat_id=chat_id,
    )
    session.add(confirmation)
    await session.commit()

    candidates = resolution.candidates
    if not candidates:
        candidates = [
            AssigneeCandidate(
                user_id=user.id,
                display_name=user.display_name,
                source="manual",
                confidence=1.0,
            )
            for user in (
                await session.execute(
                    select(m.UserModel)
                    .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
                    .where(m.TeamMemberModel.team_id == team.id)
                    .limit(6)
                )
            ).scalars()
        ]
    rows = []
    candidate_payload = []
    for index, candidate in enumerate(candidates[:6]):
        user_id = candidate.user_id
        display_name = candidate.display_name
        if user_id is None:
            continue
        candidate_payload.append({"user_id": str(user_id), "display_name": display_name})
        rows.append(
            [
                {
                    "text": display_name,
                    "callback_data": f"taskcmd:assignee:{confirmation.id}:{index}",
                }
            ]
        )
    proposal.extractor_payload = {
        **(proposal.extractor_payload or {}),
        "assignee_candidates": candidate_payload,
    }
    rows.append(
        [
            {
                "text": "Без исполнителя",
                "callback_data": f"taskcmd:no_assignee:{confirmation.id}",
            },
            {"text": "Отмена", "callback_data": f"taskcmd:cancel:{confirmation.id}"},
        ]
    )
    await session.commit()
    return ActionsResponse(
        actions=[
            SendMessageAction(
                chat_id=chat_id,
                text=(
                    f"Я не нашёл сотрудника «{resolution.raw_reference or 'не указан'}».\n\n"
                    "Выберите исполнителя:"
                ),
                reply_markup={"inline_keyboard": rows},
            )
        ]
    )


async def _handle_taskcmd_callback(container: Container, event: TelegramCallbackEvent):
    parts = event.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    cq_id = event.callback_query_id
    if action in {
        "cancel",
        "create",
        "create_anyway",
        "link",
        "no_assignee",
        "assignee",
    }:
        try:
            confirmation_id = UUID(parts[2])
        except (IndexError, ValueError):
            return _answer(cq_id, "Черновик не найден")
    else:
        return _answer(cq_id, "Действие недоступно")

    if action in {"create", "create_anyway"}:
        async with container.make_uow() as uow:
            return await ConfirmTask(
                uow, container.board, container.event_publisher, container.config
            ).execute(
                confirmation_id=confirmation_id,
                callback_query_id=cq_id,
                chat_id=event.message.chat_id,
                message_id=event.message.message_id,
                actor_telegram_id=event.from_user.id,
            )
    if action == "cancel":
        async with container.make_uow() as uow:
            return await RejectTask(uow, container.event_publisher).execute(
                confirmation_id=confirmation_id,
                callback_query_id=cq_id,
                chat_id=event.message.chat_id,
                message_id=event.message.message_id,
                actor_telegram_id=event.from_user.id,
            )

    async with container.session_factory() as session:
        confirmation = await session.get(m.ConfirmationModel, confirmation_id)
        if confirmation is None or confirmation.status != "pending":
            return _answer(cq_id, "Черновик уже закрыт")
        proposal = await session.get(m.TaskProposalModel, confirmation.proposal_id)
        if proposal is None:
            return _answer(cq_id, "Черновик не найден")
        if action == "link":
            if proposal.similar_task_id is None:
                return _answer(cq_id, "Похожая задача не найдена")
            duplicate = await session.get(m.TaskModel, proposal.similar_task_id)
            if duplicate is None:
                return _answer(cq_id, "Похожая задача не найдена")
            confirmation.status = "rejected"
            await session.commit()
            return ActionsResponse(
                actions=[
                    AnswerCallbackAction(
                        callback_query_id=cq_id,
                        text=f"Связано с {duplicate.public_id}",
                    ),
                    EditMessageAction(
                        chat_id=event.message.chat_id,
                        message_id=event.message.message_id,
                        text=(
                            "Новая карточка не создана.\n\n"
                            f"Используем существующую задачу: "
                            f"{duplicate.public_id} {duplicate.title}"
                        ),
                    ),
                ]
            )
        if action == "no_assignee":
            proposal.assignee_id = None
            proposal.assignee_text = None
        else:
            try:
                index = int(parts[3])
                candidate = (proposal.extractor_payload or {})["assignee_candidates"][index]
                user = await session.get(m.UserModel, UUID(candidate["user_id"]))
            except (IndexError, KeyError, TypeError, ValueError):
                return _answer(cq_id, "Исполнитель не найден")
            if user is None:
                return _answer(cq_id, "Исполнитель не найден")
            proposal.assignee_id = user.id
            proposal.assignee_text = user.display_name
        await session.commit()
        return ActionsResponse(
            actions=[
                AnswerCallbackAction(callback_query_id=cq_id, text="Исполнитель выбран"),
                EditMessageAction(
                    chat_id=event.message.chat_id,
                    message_id=event.message.message_id,
                    text=(
                        "Создать задачу?\n\n"
                        f"Что сделать: {proposal.title}\n"
                        f"Исполнитель: {proposal.assignee_text or 'без исполнителя'}\n"
                        "Дедлайн: "
                        f"{proposal.deadline.isoformat() if proposal.deadline else 'не указан'}"
                    ),
                    reply_markup={
                        "inline_keyboard": [
                            [
                                {
                                    "text": "Создать",
                                    "callback_data": f"taskcmd:create:{confirmation.id}",
                                },
                                {
                                    "text": "Отмена",
                                    "callback_data": f"taskcmd:cancel:{confirmation.id}",
                                },
                            ]
                        ]
                    },
                ),
            ]
        )


async def _route_v2_meeting_candidate(session, team, sender, message, parsed, event):
    from brain_api.application.use_cases.meeting_flow import _parse_time_to_dt

    meeting = parsed.get("meeting") or {}
    seq = int(await session.scalar(select(func.max(m.MeetingModel.seq))) or 0) + 1
    scheduled_at = _parse_dt(meeting.get("scheduled_at"), team.timezone)  # None, если не распознано
    # Маленькие локальные LLM часто путают дату/таймзону. Если время пустое или в
    # прошлом — берём ближайшее «HH:MM» из самого текста в таймзоне команды.
    now = datetime.now(UTC)
    if scheduled_at is None or scheduled_at < now:
        hint = _parse_time_to_dt(event.text, now, team.timezone)
        if hint is not None:
            scheduled_at = hint
    is_autonomous = bool((team.board_config or {}).get("autonomous_mode"))

    # Autonomous mode with no parseable time → ask for clarification, don't create
    if is_autonomous and scheduled_at is None:
        await session.commit()
        return ActionsResponse(actions=[
            SendMessageAction(
                chat_id=event.chat.id,
                text="🎙 Не понял время созвона. Напиши, например: «созвон в 15:00» или «созвон завтра в 18:30»",
            )
        ])

    row = m.MeetingModel(
        seq=seq,
        public_id=f"MTG-{seq}",
        team_id=team.id,
        title=meeting.get("title") or "Созвон",
        status="scheduled" if is_autonomous else "proposed",
        state="scheduled" if is_autonomous else "proposed",
        created_by=sender.id,
        scheduled_at=scheduled_at,
        scheduled_timezone=team.timezone,
        duration_minutes=int(meeting.get("duration_minutes") or 60),
        source_message_id=message.id,
        started_at=scheduled_at or datetime.now(UTC),
    )
    session.add(row)
    await session.flush()

    if is_autonomous:
        await session.commit()
        when = format_deadline(scheduled_at, team.timezone)
        return ActionsResponse(actions=[
            SendMessageAction(
                chat_id=event.chat.id,
                text=f"✅ Созвон запланирован на {when}.\n\nКто придёт?",
                reply_markup=rsvp_keyboard(row.id),
            )
        ])

    return await build_meeting_proposal(
        session,
        team,
        sender,
        row,
        event.chat.id,
        prefer_group_chat=event.chat.type in {"group", "supergroup"},
    )


async def _route_v2_daily_report(session, team, sender, message, parsed, event):
    sync = await session.scalar(
        select(m.DailySyncSessionModel).where(
            m.DailySyncSessionModel.team_id == team.id,
            m.DailySyncSessionModel.status == "open",
        )
    )
    if sync is None:
        await session.commit()
        return ActionsResponse(actions=[])
    report = parsed.get("daily_report") or {}
    session.add(
        m.DailySyncReportModel(
            sync_session_id=sync.id,
            team_id=team.id,
            user_id=sender.id,
            telegram_message_id=message.id,
            raw_text=event.text,
            parsed_summary=report.get("summary"),
            detected_status=report.get("detected_status") or "unknown",
            confidence=float(parsed["confidence"]),
        )
    )
    await session.commit()
    return _text(event.chat.id, "Отчёт принят для вечернего синка.")


async def _route_v2_absence(session, team, sender, message, parsed, event):
    absence = parsed.get("absence") or {}
    starts_at = _parse_dt(absence.get("starts_at"), team.timezone) or datetime.now(UTC)
    ends_at = _parse_dt(absence.get("ends_at"), team.timezone)
    session.add(
        m.AbsencePeriodModel(
            team_id=team.id,
            user_id=sender.id,
            reason=absence.get("reason"),
            status="active",
            starts_at=starts_at,
            ends_at=ends_at,
            source_message_id=message.id,
        )
    )
    await session.commit()
    return _text(
        event.chat.id,
        "Понял. Я не буду требовать вечерний синк в этот период, "
        "но подсвечу риски по твоим задачам.",
    )


async def _route_v2_status_update(session, container, team, sender, message, parsed, event):
    """Сотрудник пишет статус в чат → меняем статус задачи и подтверждаем."""

    detected = (parsed.get("daily_report") or {}).get("detected_status")
    if detected not in {"done", "in_progress", "blocked"}:
        await session.commit()
        return ActionsResponse(actions=[])

    # ── Поиск задачи ─────────────────────────────────────────────────────────
    task = None
    public_match = re.search(r"(?:#)?GC-\d+", event.text, flags=re.IGNORECASE)
    if public_match:
        task = await session.scalar(
            select(m.TaskModel).where(
                m.TaskModel.team_id == team.id,
                func.lower(m.TaskModel.public_id) == public_match.group(0).lstrip("#").lower(),
            )
        )
    if task is None and message.reply_to_message_id is not None:
        replied = await session.scalar(
            select(m.ChatMessageModel).where(
                m.ChatMessageModel.chat_id == message.chat_id,
                m.ChatMessageModel.telegram_message_id == message.reply_to_message_id,
            )
        )
        if replied is not None:
            task = await session.scalar(
                select(m.TaskModel).where(
                    m.TaskModel.team_id == team.id,
                    m.TaskModel.source_message_id == replied.id,
                )
            )
            if task is None:
                proposal = await session.scalar(
                    select(m.TaskProposalModel).where(
                        m.TaskProposalModel.team_id == team.id,
                        m.TaskProposalModel.source_message_id == replied.id,
                    )
                )
                if proposal is not None:
                    task = await session.scalar(
                        select(m.TaskModel).where(
                            m.TaskModel.created_from_proposal_id == proposal.id
                        )
                    )
    if task is None:
        task = await _find_task_by_keywords(session, team.id, event.text)
    if task is None:
        session.add(
            m.AIInboxItemModel(
                team_id=team.id,
                source_message_id=message.id,
                kind="low_confidence",
                status="pending",
                reason="status_update_without_task_context",
                raw_text=event.text,
                semantic_payload=parsed,
                confidence=float(parsed.get("confidence") or 0.0),
            )
        )
        await session.commit()
        return ActionsResponse(actions=[])

    # ── Обновление статуса (прямо в сессии, надёжно) ─────────────────────────
    task_public_id = task.public_id  # capture before any expire
    task_title = task.title
    task_id_cached = task.id

    task.status = detected
    task.last_status_update_at = datetime.now(UTC)
    await session.commit()

    # ── Синхронизация с доской (некритично) ─────────────────────────────────
    try:
        await TaskStatusService(container.board_mirror).update_status(
            task_id_cached,
            TaskStatus(detected),
            actor_id=sender.id,
            action="daily_report_status_update",
        )
    except Exception:
        logger.exception("Board sync failed for %s", task_public_id)

    labels = {"in_progress": "🔄 В работе", "done": "✅ Готово", "blocked": "⛔ Заблокирована"}
    return _text(event.chat.id, f"✅ {task_public_id} {task_title}\n→ {labels[detected]}")


# ── Детерминистический детектор статуса задачи (перебивает LLM-классификацию) ──

_TASK_CREATE_GUARD_RE = re.compile(
    r"\b(?:создай|добавь|поставь|назначь|создать|добавить|поставить|назначить)\s+задач",
    re.IGNORECASE,
)
_DONE_HEURISTIC_RE = re.compile(
    r"\b(?:сделал[аи]?|выполнил[аи]?|закончил[аи]?|завершил[аи]?|закрыл[аи]?|"
    r"готово?|готова|готовы|написал[аи]?|решил[аи]?|сдал[аи]?|отправил[аи]?|"
    r"запустил[аи]?|развернул[аи]?|done|finished|completed?|implement\w*)\b",
    re.IGNORECASE,
)
_PROGRESS_HEURISTIC_RE = re.compile(
    r"\b(?:приступ\w+|начинаю|начал[аи]?|взял[аи]?|берусь|делаю|работаю|работает|"
    r"in\s*progress|in-progress)\b",
    re.IGNORECASE,
)
_BLOCKED_HEURISTIC_RE = re.compile(
    r"\b(?:застрял[аи]?|заблокирован\w*|не\s+могу|проблема\s+с|blocked|stuck)\b",
    re.IGNORECASE,
)


def _detect_status_update_heuristic(text: str) -> str | None:
    """Deterministically detect task status update intent.

    Returns 'done' / 'in_progress' / 'blocked', or None if not a status update.
    Prevents LLM from misclassifying "Денис сделал задачу X" as task_candidate.
    """
    if not text:
        return None
    # Guard: task creation phrases override everything
    if _TASK_CREATE_GUARD_RE.search(text):
        return None
    if _DONE_HEURISTIC_RE.search(text):
        return "done"
    if _PROGRESS_HEURISTIC_RE.search(text):
        return "in_progress"
    if _BLOCKED_HEURISTIC_RE.search(text):
        return "blocked"
    return None


_STATUS_STOP_WORDS = frozenset({
    "что", "это", "задачу", "задача", "задание", "я", "он", "она", "мы", "вы", "они",
    "уже", "сделал", "сделала", "сделан", "сделана", "готово", "готов", "выполнил",
    "выполнила", "выполнен", "выполнена", "закрыл", "закрыла", "завершил", "завершила",
    "done", "finished", "complete", "completed", "кардинал", "cardinal", "максим",
    "привет", "всем",
})


async def _find_task_by_keywords(session, team_id, text: str):
    """Найти активную задачу по ключевым словам из сообщения (без GC-N)."""
    tokens = {
        w for w in text.lower().replace("ё", "е").split()
        if len(w) >= 4 and w not in _STATUS_STOP_WORDS
    }
    if not tokens:
        return None

    rows = await session.execute(
        select(m.TaskModel).where(
            m.TaskModel.team_id == team_id,
            m.TaskModel.status.in_(["todo", "in_progress", "blocked"]),
        )
    )
    best_task, best_score = None, 0.0
    for t in rows.scalars():
        t_tokens = {w for w in t.title.lower().replace("ё", "е").split() if len(w) >= 4}
        if not t_tokens:
            continue
        # Prefix-based matching to handle Russian word forms (запис~ / записать/запись)
        matches = sum(
            1 for mt in tokens
            if any(mt[:5] == tt[:5] or mt in tt or tt in mt for tt in t_tokens)
        )
        score = matches / max(len(tokens), len(t_tokens))
        if score > best_score and score >= 0.3:
            best_score = score
            best_task = t
    return best_task


async def _match_v2_assignee(session, team_id, assignee_text):
    if not assignee_text:
        return None
    needle = str(assignee_text).strip().lstrip("@").lower()
    rows = await session.execute(
        select(m.UserModel)
        .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
        .where(m.TeamMemberModel.team_id == team_id)
    )
    for user in rows.scalars():
        if user.telegram_username and user.telegram_username.lower() == needle:
            return user
        if user.display_name and needle in user.display_name.lower():
            return user
    return None


async def _find_v2_duplicate(session, team_id, title, assignee_id):
    tokens = {part for part in title.lower().split() if len(part) > 2}
    rows = await session.execute(
        select(m.TaskModel).where(
            m.TaskModel.team_id == team_id,
            m.TaskModel.status.in_(["todo", "in_progress", "blocked", "review"]),
        )
    )
    for task in rows.scalars():
        existing_tokens = {part for part in task.title.lower().split() if len(part) > 2}
        if not tokens or not existing_tokens:
            continue
        overlap = len(tokens & existing_tokens) / max(len(tokens), len(existing_tokens))
        same_assignee = assignee_id is None or task.assignee_id == assignee_id
        if same_assignee and overlap >= 0.72:
            return task
    return None


def _parse_dt(value, timezone: str = "UTC"):
    """ISO-строку -> aware datetime в UTC.

    naive datetime (LLM часто отдаёт без таймзоны) трактуется в таймзоне команды,
    а не в UTC — иначе «18:00» уезжает на смещение пояса.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        tz: tzinfo
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = UTC
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(UTC)


def _display_name_from_event(event: TelegramMessageEvent | TelegramCommandEvent) -> str:
    parts = [part for part in (event.sender.first_name, event.sender.last_name) if part]
    return " ".join(parts) or event.sender.username or f"user{event.sender.id}"


@router.post("/command", response_model=ActionsResponse)
async def ingest_command(
    event: TelegramCommandEvent,
    container: Container = Depends(get_container),
) -> ActionsResponse:
    command = event.command.lower()
    chat_id = event.chat.id
    is_group = event.chat.type in ("group", "supergroup", "channel")

    # ── /start — главное меню с кнопками ─────────────────────────────────
    if command == "start":
        if is_group:
            if not hasattr(container, "session_factory"):
                async with container.make_uow() as uow:
                    project = await uow.projects.ensure_default(
                        container.config.default_workspace_name
                    )
                    await uow.chats.upsert(chat_id, event.chat.type, event.chat.title, project.id)
                    bound_chat = await uow.chats.get_by_telegram_id(chat_id)
                    if bound_chat is None:
                        raise RuntimeError("chat binding failed")
                    await uow.projects.set_default_chat(project.id, bound_chat.id)
                    await uow.commit()
                return ActionsResponse(
                    actions=[
                        SendMessageAction(
                            chat_id=chat_id,
                            text=_WELCOME_GROUP,
                            parse_mode="Markdown",
                            reply_markup=_confirmation_mode_kb(),
                        )
                    ]
                )
            async with container.session_factory() as session:
                chat = await session.scalar(
                    select(m.TelegramChatModel).where(
                        m.TelegramChatModel.telegram_chat_id == chat_id
                    )
                )
                if chat is None or chat.team_id is None:
                    return _text(chat_id, _UNBOUND_TEAM_TEXT)
            return ActionsResponse(
                actions=[
                    SendMessageAction(
                        chat_id=chat_id,
                        text=_WELCOME_GROUP,
                        parse_mode="Markdown",
                        reply_markup=_main_menu_kb(is_group=True),
                    )
                ]
            )
        return ActionsResponse(
            actions=[
                SendMessageAction(
                    chat_id=chat_id,
                    text=_WELCOME_PRIVATE,
                    parse_mode="Markdown",
                    reply_markup=_main_menu_kb(is_group=False),
                )
            ]
        )

    # ── Материалы по задаче: /howto, /material, /help <тема|GC-id> ───────
    if command in ("howto", "material", "materials"):
        topic = " ".join(event.args).strip()
        if not topic:
            return _text(chat_id, "Укажи тему: /howto написать REST API на FastAPI")
        async with container.session_factory() as session:
            return _html(chat_id, await materials_for_arg(session, topic))

    if command == "help":
        if event.args:
            async with container.session_factory() as session:
                return _html(chat_id, await materials_for_arg(session, " ".join(event.args)))
        return ActionsResponse(
            actions=[
                SendMessageAction(
                    chat_id=chat_id,
                    text=_HELP_TEXT,
                    parse_mode="HTML",
                    reply_markup=_back_kb(),
                )
            ]
        )

    # ── Визуальное меню настроек команды ─────────────────────────────────
    if command == "settings":
        async with container.session_factory() as session:
            return await open_settings(session, chat_id)

    if command == "task":
        task_text = " ".join(event.args).strip()
        if not task_text:
            return _text(
                chat_id,
                "Формат: /task @username подготовить отчёт до завтра 18:00",
            )
        mode = (
            InteractionMode.REPLY_TASK_COMMAND
            if event.reply_to_message_id is not None
            else InteractionMode.EXPLICIT_TASK_COMMAND
        )
        response = await _try_v2_semantic_message(
            event,
            container,
            interaction_mode=mode,
            semantic_text=task_text,
        )
        return response or _text(chat_id, "Команда /task доступна в привязанном чате команды.")

    if command in {"leaderboard", "rating", "top"}:
        async with container.session_factory() as session:
            return _text(chat_id, await team_leaderboard_text_for_chat(session, chat_id))

    if command in {"report", "reports"}:
        async with container.session_factory() as session:
            text, keyboard = await manager_report_menu(session, event.sender.id)
        return ActionsResponse(
            actions=[
                SendMessageAction(
                    chat_id=event.sender.id,
                    text=text,
                    reply_markup=keyboard,
                )
            ]
        )

    if command == "bind_team":
        if not event.args:
            return _text(chat_id, "Формат: /bind_team CODE")
        return await bind_team_chat(
            TelegramBindTeamRequest(
                code=event.args[0],
                tg_chat_id=chat_id,
                chat_id=chat_id,
                chat_type=event.chat.type,
                title=event.chat.title,
                linked_by_tg_user_id=event.sender.id,
            ),
            container,
        )

    # ── /jira URL EMAIL TOKEN PROJECT ────────────────────────────────────
    if command == "jira":
        args = event.args
        if len(args) < 4:
            return _md(chat_id, _JIRA_SETUP_TEXT, _back_kb())
        jira_url, email, token, project_key = args[0], args[1], args[2], args[3]
        # Store in env (runtime — in-memory for demo; persistent via .env in prod)
        import os

        os.environ["JIRA_URL"] = jira_url
        os.environ["JIRA_EMAIL"] = email
        os.environ["JIRA_API_TOKEN"] = token
        os.environ["JIRA_PROJECT_KEY"] = project_key
        os.environ["BOARD_PROVIDER"] = "jira"
        return _md(
            chat_id,
            f"✅ *Jira подключена!*\n\n"
            f"URL: `{jira_url}`\n"
            f"Проект: `{project_key}`\n\n"
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
        # Post a short message + link to a site page instead of a wall of text.
        full_text = actions.actions[0].text if actions.actions else ""
        try:
            from brain_api.application.use_cases.meeting_summary import (
                create_share_link,
                public_base,
            )

            async with container.session_factory() as session:
                team = await session.scalar(
                    select(m.TeamModel).where(m.TeamModel.tg_chat_id == chat_id)
                )
                token = await create_share_link(
                    session,
                    kind="digest",
                    team_id=team.id if team else None,
                    ref_id=None,
                    title="Вечерний дайджест",
                    payload={"text": full_text},
                )
                await session.commit()
            url = f"{public_base(get_settings())}/s.html?t={token}"
            return _text(chat_id, f"🌙 Вечерний дайджест готов\n\n🔗 Открыть: {url}")
        except Exception:
            return actions

    # ── /tasks ────────────────────────────────────────────────────────────
    if command == "tasks":
        async with container.make_uow() as uow:
            return await ListTasks(uow, container.config).execute(chat_id)

    if command == "tasks_all":
        async with container.make_uow() as uow:
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

    # ── Task status commands ──────────────────────────────────────────────
    _STATUS_COMMANDS = {"start_task", "block", "done"}
    if command in _STATUS_COMMANDS:
        return await _handle_v2_status_command(
            container, command, event.args, chat_id, event.sender.id
        )

    # ── Meeting commands ──────────────────────────────────────────────────
    if command == "meeting_start":
        async with container.make_uow() as uow:
            meeting = await start_meeting(
                uow,
                container.config,
                telegram_chat_id=chat_id,
                chat_type=event.chat.type,
                chat_title=event.chat.title,
                external_source="telegram",
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
        return _md(
            chat_id,
            f"⏹ *Встреча завершена* `{active.public_id}`\n"
            f"Реплик: {dto.transcript_count} | Задач: {dto.proposal_count}",
            _meetings_kb(),
        )

    if command == "meeting_status":
        async with container.make_uow() as uow:
            active = await uow.meetings.get_active_for_chat(chat_id)
            if active is None:
                return _text(chat_id, "Нет активной встречи.")
            dto = await meeting_response(uow, active)
        return _md(
            chat_id,
            f"📊 *Встреча* `{active.public_id}`\nСтарт: {active.started_at:%H:%M}\n"
            f"Реплик: {dto.transcript_count} | Задач: {dto.proposal_count}",
            _meetings_kb(),
        )

    # ── Demo commands ─────────────────────────────────────────────────────
    if command == "demo_start":
        async with container.make_uow() as uow:
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
            f"🚀 Демо запущено. Встреча {meeting.public_id}. Предложения задач появятся выше.",
        )

    if command == "demo_reset":
        if container.settings.app_env != "dev":
            return _text(chat_id, "Demo reset доступен только в dev.")
        async with container.make_uow() as uow:
            result = await uow.debug.reset_demo()
            await uow.commit()
        return _text(
            chat_id,
            f"Очищено: Встреч: {result['meetings']}, реплик: {result['transcripts']}.",
        )

    if command in ("unlink", "unbind", "logout"):
        return await _handle_unlink_command(container, event, is_group)

    if command in ("summary", "саммари", "итоги"):
        return await _handle_summary_command(container, event)

    if command == "bind_chat":
        if container.settings.app_env == "dev":
            async with container.make_uow() as uow:
                project = await uow.projects.ensure_default(container.config.default_workspace_name)
                await uow.chats.upsert(chat_id, event.chat.type, event.chat.title, project.id)
                bound_chat = await uow.chats.get_by_telegram_id(chat_id)
                if bound_chat is None:
                    raise RuntimeError("chat binding failed")
                await uow.projects.set_default_chat(project.id, bound_chat.id)
                await uow.commit()
            return _text(chat_id, f"✅ Чат привязан к dev workspace: {project.name}")
        return _text(chat_id, _UNBOUND_TEAM_TEXT)

    return ActionsResponse(
        actions=[
            SendMessageAction(
                chat_id=chat_id,
                text=f"Неизвестная команда /{command}. Нажми /start для меню.",
            )
        ]
    )


async def _handle_summary_command(
    container: Container, event: TelegramCommandEvent
) -> ActionsResponse:
    """Generate a summary for the team's latest meeting and post a short link."""
    from brain_api.application.use_cases.meeting_summary import generate_meeting_summary

    chat_id = event.chat.id
    settings = get_settings()
    async with container.session_factory() as session:
        team = await session.scalar(
            select(m.TeamModel).where(m.TeamModel.tg_chat_id == chat_id)
        )
        if team is None:
            return _text(chat_id, "Этот чат не привязан к команде Grey Cardinal.")
        meeting = await session.scalar(
            select(m.MeetingModel)
            .where(m.MeetingModel.team_id == team.id)
            .order_by(m.MeetingModel.created_at.desc())
        )
        if meeting is None:
            return _text(chat_id, "Пока нет созвонов для саммари.")
        result = await generate_meeting_summary(session, settings, meeting)
        await session.commit()
    short = (result.get("summary") or "").strip()
    if len(short) > 160:
        short = short[:157] + "…"
    text = f"📝 Саммари созвона «{result['title']}»\n\n{short}\n\n🔗 Подробнее: {result['url']}"
    return _text(chat_id, text)


async def _handle_unlink_command(
    container: Container,
    event: TelegramCommandEvent,
    is_group: bool,
) -> ActionsResponse:
    """Отвязать Telegram: в личке — аккаунт пользователя, в группе — чат от команды."""
    chat_id = event.chat.id
    async with container.session_factory() as session:
        if is_group:
            team = await session.scalar(
                select(m.TeamModel).where(m.TeamModel.tg_chat_id == chat_id)
            )
            chat = await session.scalar(
                select(m.TelegramChatModel).where(
                    m.TelegramChatModel.telegram_chat_id == chat_id
                )
            )
            if team is None and (chat is None or chat.team_id is None):
                return _text(chat_id, "Этот чат и так не привязан к команде.")
            if team is not None:
                team.tg_chat_id = None
            if chat is not None:
                chat.team_id = None
            await session.commit()
            return _text(
                chat_id,
                "✅ Чат отвязан от команды. Я больше не буду собирать здесь задачи. "
                "Чтобы привязать снова — /bind_team CODE.",
            )

        # Личка: отвязываем аккаунт пользователя.
        user = await session.scalar(
            select(m.UserModel).where(m.UserModel.telegram_user_id == event.sender.id)
        )
        if user is None or user.telegram_user_id is None:
            return _text(chat_id, "Ваш аккаунт и так не привязан к Telegram.")
        user.telegram_user_id = None
        user.telegram_username = None
        await session.commit()
        return _text(
            chat_id,
            "✅ Telegram-аккаунт отвязан. Уведомления приходить не будут. "
            "Чтобы привязать снова — откройте кабинет и нажмите «Привязать Telegram».",
        )


async def _handle_v2_status_command(
    container: Container,
    command: str,
    args: list[str],
    chat_id: int,
    actor_telegram_id: int,
) -> ActionsResponse:
    new_status = status_for_command(command)
    if new_status is None:
        return _text(chat_id, "Неизвестная команда изменения статуса.")
    if not args:
        return _text(chat_id, f"Укажи задачу, например: /{command} GC-12")
    sequence = parse_public_id(args[0])
    async with container.session_factory() as session:
        chat = await session.scalar(
            select(m.TelegramChatModel).where(m.TelegramChatModel.telegram_chat_id == chat_id)
        )
        if chat is None or chat.team_id is None:
            return _text(chat_id, _UNBOUND_TEAM_TEXT)
        statement = select(m.TaskModel).where(m.TaskModel.team_id == chat.team_id)
        if sequence is not None:
            statement = statement.where(m.TaskModel.public_id == format_public_id(sequence))
        else:
            try:
                statement = statement.where(m.TaskModel.id == UUID(args[0]))
            except ValueError:
                return _text(chat_id, f"Задача {args[0]} не найдена.")
        task = await session.scalar(statement)
        if task is None:
            return _text(chat_id, f"Задача {args[0]} не найдена.")
        task_id = task.id
    result = await TaskStatusService(container.board_mirror).update_status(
        task_id,
        new_status,
        actor_id=actor_telegram_id,
        action="telegram_status_command",
    )
    text = f"✅ {result.public_id} → {result.status}"
    if result.sync_status == "error":
        text = f"{text}\n\nYouGile sync error: {result.sync_error}"
    return _text(chat_id, text)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_callback(data: str) -> tuple[str, UUID | None]:
    if ":" not in data:
        return data, None
    action, _, raw_id = data.partition(":")
    try:
        return action, UUID(raw_id)
    except ValueError:
        return action, None


_TELEMOST_NOTICE = (
    "ℹ️ Если включён meeting agent Grey Cardinal, он может подключиться для "
    "заметок и задач."
)


async def _handle_telemost_callback(
    container: Container, event: TelegramCallbackEvent
) -> ActionsResponse:
    """Inline-кнопки выбора провайдера созвона.

    Проверяет: чат привязан к команде, Телемост подключён, право инициировать.
    Сам создаёт комнату только по явному нажатию пользователя (не автоматически).
    """
    cq_id = event.callback_query_id
    chat_id = event.message.chat_id
    msg_id = event.message.message_id

    if event.data == CB_TELEMOST_DISMISS:
        return ActionsResponse(
            actions=[
                AnswerCallbackAction(callback_query_id=cq_id, text="Ок"),
                EditMessageAction(
                    chat_id=chat_id, message_id=msg_id, text="Хорошо, без созвона."
                ),
            ]
        )

    settings = get_settings()
    provider_label = "Яндекс Телемост"
    async with container.session_factory() as session:
        team = await session.scalar(
            select(m.TeamModel).where(m.TeamModel.tg_chat_id == chat_id)
        )
        result: dict | None = None

        # 1) Try Yandex Telemost first if a team has it connected.
        if team is not None:
            integration = await telemost_svc.get_integration(session, team.id)
            if integration is not None and integration.status == "connected":
                try:
                    result = await telemost_svc.create_room_for_chat(
                        session,
                        settings,
                        telegram_chat_id=chat_id,
                        created_by_telegram_user_id=event.from_user.id,
                    )
                except (telemost_svc.TelemostNotConnected, YandexTelemostError) as exc:
                    # Telemost unavailable (e.g. 403 no API access) → fall back.
                    logger.warning(
                        "[telemost] room creation failed; using Jitsi fallback: %s",
                        exc,
                    )
                    await session.rollback()
                    result = None

        # 2) Fallback: Jitsi public room (no OAuth). Works for any chat.
        if result is None or not result.get("join_url"):
            result = await telemost_svc.create_jitsi_room_for_chat(
                session,
                telegram_chat_id=chat_id,
                created_by_telegram_user_id=event.from_user.id,
            )
            provider_label = "Видеовстреча (Jitsi)"

        await session.commit()

    join_url = result.get("join_url")
    if not join_url:
        return ActionsResponse(
            actions=[
                AnswerCallbackAction(callback_query_id=cq_id, text="Ошибка"),
                SendMessageAction(
                    chat_id=chat_id,
                    text="Не удалось создать ссылку на встречу. Попробуйте позже.",
                ),
            ]
        )

    actions: list = [
        AnswerCallbackAction(callback_query_id=cq_id, text="Готово"),
        EditMessageAction(
            chat_id=chat_id, message_id=msg_id, text="📹 Создаю ссылку на созвон…"
        ),
        SendMessageAction(
            chat_id=chat_id,
            text=(
                f"✅ Созвон готов — {provider_label}\n\n"
                f"Ссылка: {join_url}\n\n"
                f"{_TELEMOST_NOTICE}"
            ),
        ),
    ]
    # Сразу запускаем опрос «Кто придёт?» по созданной встрече.
    meeting_id = result.get("meeting_id")
    if meeting_id is not None:
        actions.append(
            SendMessageAction(
                chat_id=chat_id,
                text="📊 Кто придёт на созвон?",
                reply_markup=rsvp_keyboard(meeting_id),
            )
        )
    return ActionsResponse(actions=actions)


def _text(chat_id: int, text: str) -> ActionsResponse:
    return ActionsResponse(actions=[SendMessageAction(chat_id=chat_id, text=text)])


def _html(chat_id: int, text: str) -> ActionsResponse:
    return ActionsResponse(actions=[
        SendMessageAction(chat_id=chat_id, text=text, parse_mode="HTML")
    ])


def _telegram_display_name(payload: TelegramLinkRequest) -> str:
    parts = [p for p in (payload.first_name, payload.last_name) if p]
    if parts:
        return " ".join(parts)
    return payload.username or f"user{payload.tg_user_id}"


def _md(chat_id: int, text: str, kb: dict | None = None) -> ActionsResponse:
    return ActionsResponse(
        actions=[
            SendMessageAction(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        ]
    )


def _answer(cq_id: str, text: str) -> ActionsResponse:
    return ActionsResponse(actions=[AnswerCallbackAction(callback_query_id=cq_id, text=text)])


def _edit_with_kb(chat_id: int, msg_id: int, cq_id: str, text: str, kb: dict) -> ActionsResponse:
    from grey_cardinal_contracts import EditMessageAction

    return ActionsResponse(
        actions=[
            AnswerCallbackAction(callback_query_id=cq_id, text=""),
            EditMessageAction(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=kb,
                parse_mode="Markdown",
            ),
        ]
    )


def _answer_and_edit(
    cq_id: str, chat_id: int, msg_id: int, result: ActionsResponse
) -> ActionsResponse:
    return ActionsResponse(
        actions=[
            AnswerCallbackAction(callback_query_id=cq_id, text=""),
            *result.actions,
        ]
    )


def _answer_and_add(cq_id: str, result: ActionsResponse) -> ActionsResponse:
    return ActionsResponse(
        actions=[
            AnswerCallbackAction(callback_query_id=cq_id, text=""),
            *result.actions,
        ]
    )
