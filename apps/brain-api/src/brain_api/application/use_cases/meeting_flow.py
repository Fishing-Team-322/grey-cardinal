"""V2 meeting (созвон) flow для Telegram-бота.

Сценарий 2 (руководитель):
  1. В чате команды звучит «давайте созвон в 18:00» — semantic-слой ловит
     `meeting_candidate` и создаёт MeetingModel(state="proposed").
  2. Бот пишет руководителю в личку: «Создаём созвон в 18:00?» с кнопками
     подтверждения. Если время не распозналось — просит вписать время в личке.
  3. После подтверждения бот публикует в чат команды опрос «Кто придёт?» с
     RSVP-кнопками. Голоса собираются в MeetingRsvpModel, опрос обновляется.
  4. За ~5 минут до начала планировщик пишет в личку каждому, кто отметился
     «Приду», что пора запускать даемон (см. scheduler.jobs.run_meeting_reminders).

Весь интерактив (шаги 2–3) реализован через возвращаемые BotAction — telegram-bot
их исполняет. Поэтому модуль не зависит от gateway и полностью тестируется офлайн.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from brain_api.application.rendering import format_deadline
from brain_api.infrastructure.db import models as m
from grey_cardinal_contracts import (
    ActionsResponse,
    AnswerCallbackAction,
    EditMessageAction,
    SendMessageAction,
    TelegramCallbackEvent,
    TelegramSender,
)

# ── Callback-data префиксы созвонов ───────────────────────────────────────────
CB_MTG_OK = "mtg_ok"      # руководитель подтверждает время
CB_MTG_NO = "mtg_no"      # руководитель отменяет
CB_MTG_TIME = "mtg_time"  # руководитель хочет вписать другое время
CB_RSVP_YES = "rsvp_yes"
CB_RSVP_NO = "rsvp_no"
CB_RSVP_MAYBE = "rsvp_maybe"

MEETING_CB_PREFIXES = (
    f"{CB_MTG_OK}:",
    f"{CB_MTG_NO}:",
    f"{CB_MTG_TIME}:",
    f"{CB_RSVP_YES}:",
    f"{CB_RSVP_NO}:",
    f"{CB_RSVP_MAYBE}:",
)

_TIME_RE = re.compile(
    r"\b(?:в|к|на)?\s*(\d{1,2})\s*[:.\-\s]\s*(\d{2})\b"
    r"|\b(?:в|к|на)\s+(\d{1,2})\b",
    re.IGNORECASE,
)


def is_meeting_callback(data: str) -> bool:
    return data.startswith(MEETING_CB_PREFIXES)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _answer(cq_id: str, text: str, alert: bool = False) -> AnswerCallbackAction:
    return AnswerCallbackAction(callback_query_id=cq_id, text=text, show_alert=alert)


def _when(meeting: m.MeetingModel, team: m.TeamModel) -> str:
    if meeting.scheduled_at is None:
        return "время не задано"
    return format_deadline(meeting.scheduled_at, team.timezone)


def _confirm_keyboard(meeting_id: UUID) -> dict:
    mid = str(meeting_id)
    return {
        "inline_keyboard": [
            [{"text": "✅ Да, создаём", "callback_data": f"{CB_MTG_OK}:{mid}"}],
            [{"text": "🕐 Другое время", "callback_data": f"{CB_MTG_TIME}:{mid}"}],
            [{"text": "❌ Отмена", "callback_data": f"{CB_MTG_NO}:{mid}"}],
        ]
    }


def rsvp_keyboard(meeting_id: UUID) -> dict:
    mid = str(meeting_id)
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Приду", "callback_data": f"{CB_RSVP_YES}:{mid}"},
                {"text": "❌ Не приду", "callback_data": f"{CB_RSVP_NO}:{mid}"},
            ],
            [{"text": "🤔 Возможно", "callback_data": f"{CB_RSVP_MAYBE}:{mid}"}],
        ]
    }


# Backwards-compatible alias (internal callers).
_rsvp_keyboard = rsvp_keyboard


async def _manager_for_team(
    session, team_id: UUID, prefer_user_id: UUID | None
) -> m.UserModel | None:
    """Найти руководителя команды с привязанным Telegram (для личного сообщения)."""
    rows = await session.execute(
        select(m.UserModel)
        .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
        .where(
            m.TeamMemberModel.team_id == team_id,
            m.TeamMemberModel.role == "manager",
            m.UserModel.telegram_user_id.is_not(None),
        )
    )
    managers = list(rows.scalars())
    if not managers:
        return None
    if prefer_user_id is not None:
        for mgr in managers:
            if mgr.id == prefer_user_id:
                return mgr
    return managers[0]


async def _get_or_create_user(session, sender: TelegramSender) -> m.UserModel:
    user = await session.scalar(
        select(m.UserModel).where(m.UserModel.telegram_user_id == sender.id)
    )
    if user is not None:
        return user
    parts = [p for p in (sender.first_name, sender.last_name) if p]
    user = m.UserModel(
        telegram_user_id=sender.id,
        telegram_username=sender.username,
        display_name=" ".join(parts) or sender.username or f"user{sender.id}",
    )
    session.add(user)
    await session.flush()
    return user


def _send(chat_id: int, text: str, kb: dict | None = None) -> SendMessageAction:
    return SendMessageAction(chat_id=chat_id, text=text, reply_markup=kb)


# ── Шаг 2: предложение созвона руководителю ──────────────────────────────────

async def build_meeting_proposal(
    session,
    team: m.TeamModel,
    sender: m.UserModel,
    meeting: m.MeetingModel,
    group_chat_id: int,
    *,
    prefer_group_chat: bool = False,
) -> ActionsResponse:
    """Сформировать подтверждение созвона: ЛС руководителю либо запрос в чат."""
    manager = await _manager_for_team(session, team.id, prefer_user_id=sender.id)

    # Куда отправлять подтверждение: в личку руководителю, иначе — в чат команды.
    target_chat = group_chat_id
    if not prefer_group_chat:
        target_chat = (
            manager.telegram_user_id if manager is not None else None
        ) or group_chat_id

    if meeting.scheduled_at is None:
        # Время не распозналось — просим вписать его (stateful в личке).
        meta = dict(meeting.metadata_json or {})
        meta["awaiting_time_from"] = manager.telegram_user_id if manager else None
        meeting.metadata_json = meta
        await session.commit()
        return ActionsResponse(actions=[
            _send(
                target_chat,
                "🎙 Похоже, планируется созвон, но я не понял время.\n"
                "Напиши, во сколько — например: 18:30",
            )
        ])

    text = (
        "🎙 Планируем созвон\n\n"
        f"Когда: {_when(meeting, team)}\n"
        f"Команда: {team.name}\n\n"
        "Создаём и зовём команду?"
    )
    await session.commit()
    return ActionsResponse(actions=[_send(target_chat, text, _confirm_keyboard(meeting.id))])


# ── Шаг 2b: руководитель вписал другое время в личке ─────────────────────────

async def handle_pending_meeting_time(
    session, sender: TelegramSender, text: str, now: datetime
) -> ActionsResponse | None:
    """Если у пользователя есть созвон в статусе «жду время» — применить введённое время."""
    user = await session.scalar(
        select(m.UserModel).where(m.UserModel.telegram_user_id == sender.id)
    )
    if user is None:
        return None
    meeting = await session.scalar(
        select(m.MeetingModel)
        .where(m.MeetingModel.created_by == user.id, m.MeetingModel.state == "proposed")
        .order_by(m.MeetingModel.created_at.desc())
    )
    if meeting is None or not (meeting.metadata_json or {}).get("awaiting_time_from"):
        return None

    scheduled = _parse_time_to_dt(text, now, meeting.scheduled_timezone or "Europe/Moscow")
    if scheduled is None:
        return ActionsResponse(actions=[
            _send(sender.id, "Не понял время. Напиши, например: 18:30 или «в 19»")
        ])

    team = await session.get(m.TeamModel, meeting.team_id)
    meeting.scheduled_at = scheduled
    meta = dict(meeting.metadata_json or {})
    meta.pop("awaiting_time_from", None)
    meeting.metadata_json = meta
    await session.commit()
    text_out = (
        "🎙 Планируем созвон\n\n"
        f"Когда: {_when(meeting, team)}\n"
        f"Команда: {team.name}\n\n"
        "Создаём и зовём команду?"
    )
    return ActionsResponse(actions=[_send(sender.id, text_out, _confirm_keyboard(meeting.id))])


# ── Шаг 3: callback'и подтверждения и RSVP ───────────────────────────────────

async def handle_meeting_callback(
    session, data: str, event: TelegramCallbackEvent
) -> ActionsResponse:
    action, _, raw_id = data.partition(":")
    try:
        meeting_id = UUID(raw_id)
    except ValueError:
        return ActionsResponse(actions=[_answer(event.callback_query_id, "Некорректный созвон")])

    meeting = await session.get(m.MeetingModel, meeting_id)
    if meeting is None:
        return ActionsResponse(actions=[_answer(event.callback_query_id, "Созвон не найден")])
    team = await session.get(m.TeamModel, meeting.team_id)

    if action == CB_MTG_OK:
        return await _confirm_meeting(session, meeting, team, event)
    if action == CB_MTG_NO:
        return await _cancel_meeting(session, meeting, event)
    if action == CB_MTG_TIME:
        return await _request_other_time(session, meeting, event)
    if action in (CB_RSVP_YES, CB_RSVP_NO, CB_RSVP_MAYBE):
        return await _record_rsvp(session, meeting, team, event, action)

    return ActionsResponse(actions=[_answer(event.callback_query_id, "Неизвестное действие")])


async def _confirm_meeting(
    session, meeting: m.MeetingModel, team: m.TeamModel, event: TelegramCallbackEvent
) -> ActionsResponse:
    meeting.state = "scheduled"
    meeting.status = "scheduled"
    await session.commit()

    actions: list = [
        _answer(event.callback_query_id, "Созвон создан"),
        EditMessageAction(
            chat_id=event.message.chat_id,
            message_id=event.message.message_id,
            text=f"✅ Созвон назначен на {_when(meeting, team)}. Опрос отправлен в чат команды.",
        ),
    ]
    if team is not None and team.tg_chat_id is not None:
        poll_text = (
            f"📊 Созвон {_when(meeting, team)}\n\n"
            f"{meeting.title or 'Созвон'}\n\n"
            "Кто придёт?"
        )
        actions.append(_send(team.tg_chat_id, poll_text, _rsvp_keyboard(meeting.id)))
    return ActionsResponse(actions=actions)


async def _cancel_meeting(
    session, meeting: m.MeetingModel, event: TelegramCallbackEvent
) -> ActionsResponse:
    meeting.state = "cancelled"
    meeting.status = "cancelled"
    await session.commit()
    return ActionsResponse(actions=[
        _answer(event.callback_query_id, "Отменено"),
        EditMessageAction(
            chat_id=event.message.chat_id,
            message_id=event.message.message_id,
            text="❌ Созвон отменён.",
        ),
    ])


async def _request_other_time(
    session, meeting: m.MeetingModel, event: TelegramCallbackEvent
) -> ActionsResponse:
    meta = dict(meeting.metadata_json or {})
    meta["awaiting_time_from"] = event.from_user.id
    meeting.metadata_json = meta
    await session.commit()
    return ActionsResponse(actions=[
        _answer(event.callback_query_id, ""),
        EditMessageAction(
            chat_id=event.message.chat_id,
            message_id=event.message.message_id,
            text="🕐 Напиши новое время — например: 18:30",
        ),
    ])


async def _record_rsvp(
    session,
    meeting: m.MeetingModel,
    team: m.TeamModel,
    event: TelegramCallbackEvent,
    action: str,
) -> ActionsResponse:
    status = {CB_RSVP_YES: "yes", CB_RSVP_NO: "no", CB_RSVP_MAYBE: "maybe"}[action]
    user = await _get_or_create_user(session, event.from_user)

    rsvp = await session.scalar(
        select(m.MeetingRsvpModel).where(
            m.MeetingRsvpModel.meeting_id == meeting.id,
            m.MeetingRsvpModel.user_id == user.id,
        )
    )
    if rsvp is None:
        session.add(m.MeetingRsvpModel(meeting_id=meeting.id, user_id=user.id, status=status))
    else:
        rsvp.status = status
    await session.commit()

    yes, no, maybe = await _rsvp_counts(session, meeting.id)
    label = {"yes": "Приду", "no": "Не приду", "maybe": "Возможно"}[status]
    poll_text = (
        f"📊 Созвон {_when(meeting, team)}\n\n"
        f"{meeting.title or 'Созвон'}\n\n"
        "Кто придёт?\n\n"
        f"✅ Придут: {yes}   ❌ Нет: {no}   🤔 Возможно: {maybe}"
    )
    return ActionsResponse(actions=[
        _answer(event.callback_query_id, f"Записал: {label}"),
        EditMessageAction(
            chat_id=event.message.chat_id,
            message_id=event.message.message_id,
            text=poll_text,
            reply_markup=_rsvp_keyboard(meeting.id),
        ),
    ])


async def _rsvp_counts(session, meeting_id: UUID) -> tuple[int, int, int]:
    rows = await session.execute(
        select(m.MeetingRsvpModel.status).where(m.MeetingRsvpModel.meeting_id == meeting_id)
    )
    yes = no = maybe = 0
    for (status,) in rows.all():
        if status == "yes":
            yes += 1
        elif status == "no":
            no += 1
        elif status == "maybe":
            maybe += 1
    return yes, no, maybe


def _parse_time_to_dt(text: str, now: datetime, timezone: str) -> datetime | None:
    from zoneinfo import ZoneInfo

    match = _TIME_RE.search(text)
    if match is None:
        return None
    if match.group(1) is not None:
        hour, minute = int(match.group(1)), int(match.group(2))
    else:
        hour, minute = int(match.group(3)), 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    tz = ZoneInfo(timezone)
    local_now = now.astimezone(tz)
    target = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= local_now:
        target += timedelta(days=1)
    return target.astimezone(UTC)
