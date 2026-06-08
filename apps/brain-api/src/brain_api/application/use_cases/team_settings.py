"""Визуальное меню настроек команды (как у BotFather) — `/settings`.

Сейчас настраивается расписание дайджеста задач (когда бот прогоняет/присылает
сводку по задачам команды). Хранится per-team в `teams.board_config["digest_mode"]`.
Всё в brain-api: бот лишь рисует возвращённые inline-кнопки.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from brain_api.infrastructure.db import models as m
from grey_cardinal_contracts import (
    ActionsResponse,
    AnswerCallbackAction,
    EditMessageAction,
    SendMessageAction,
)

CB_SET_DIGEST = "cfg_dig"   # cfg_dig:<mode>
CB_SET_CARDINAL_MENTION = "cfg_cardinal:toggle"
CB_SET_AUTONOMOUS = "cfg_auto:toggle"
CB_SET_CLOSE = "cfg_close"
CARDINAL_MENTION_SETTING = "require_cardinal_mention"
AUTONOMOUS_MODE_SETTING = "autonomous_mode"
DEFAULT_REQUIRE_CARDINAL_MENTION = False

_CARDINAL_PREFIX = re.compile(
    r"^\s*(?:(?:так|ну|ээ+|эм+|слушай|слушайте)[\s,.:;!?—-]+)?"
    r"(?:серый\s+)?(?:кардинал|кординал|координат[ауеы]?|cardinal|dinal)"
    r"(?=$|[\s,.:;!?—-])[\s,.:;!?—-]*",
    re.IGNORECASE,
)

# mode -> (label, [часы по таймзоне команды])
DIGEST_MODES: dict[str, tuple[str, list[int]]] = {
    "morning": ("Утром (09:00)", [9]),
    "evening": ("Вечером (20:00)", [20]),
    "both": ("Утром и вечером", [9, 20]),
    "thrice": ("3 раза (09:00 / 14:00 / 19:00)", [9, 14, 19]),
    "off": ("Выключено", []),
}
DEFAULT_MODE = "off"


def digest_slots(mode: str) -> list[int]:
    return DIGEST_MODES.get(mode, DIGEST_MODES[DEFAULT_MODE])[1]


def require_cardinal_mention(team: m.TeamModel) -> bool:
    return bool((team.board_config or {}).get(
        CARDINAL_MENTION_SETTING,
        DEFAULT_REQUIRE_CARDINAL_MENTION,
    ))


def autonomous_mode_enabled(team: m.TeamModel) -> bool:
    return bool((team.board_config or {}).get(AUTONOMOUS_MODE_SETTING, False))


def addressed_message_text(text: str, *, required: bool) -> str | None:
    """Return command text without the leading bot name, or None when ignored."""
    if not required:
        return text
    match = _CARDINAL_PREFIX.match(text)
    if match is None:
        return None
    command = text[match.end():].strip()
    return command or None


def _settings_text(team: m.TeamModel, mode: str, cardinal_required: bool) -> str:
    label = DIGEST_MODES.get(mode, DIGEST_MODES[DEFAULT_MODE])[0]
    mention_label = "только после «Кардинал, ...»" if cardinal_required else "все сообщения"
    autonomous = autonomous_mode_enabled(team)
    autonomous_label = "включён (без подтверждений)" if autonomous else "выключен (с подтверждением)"
    return (
        f"⚙️ Настройки команды «{team.name}»\n"
        f"Часовой пояс: {team.timezone}\n\n"
        f"🤖 Реакция бота: {mention_label}\n"
        f"🔔 Дайджест задач: {label}\n"
        f"⚡ Автономный режим: {autonomous_label}\n\n"
        "В режиме обращения по имени бот игнорирует обычные сообщения и реагирует "
        "только на сообщения, начинающиеся с «Кардинал».\n\n"
        "Выбери настройки:"
    )


def _settings_keyboard(current: str, cardinal_required: bool, autonomous: bool = False) -> dict:
    rows = []
    auto_mark = "⚡ ✅" if autonomous else "⚡ ⬜"
    rows.append([{
        "text": f"{auto_mark} Автономный режим (без подтверждений)",
        "callback_data": CB_SET_AUTONOMOUS,
    }])
    mention_mark = "✅" if cardinal_required else "⬜"
    rows.append([{
        "text": f"{mention_mark} Отвечать только на «Кардинал, ...»",
        "callback_data": CB_SET_CARDINAL_MENTION,
    }])
    for mode, (label, _slots) in DIGEST_MODES.items():
        mark = "✅ " if mode == current else ""
        rows.append([{"text": f"{mark}{label}", "callback_data": f"{CB_SET_DIGEST}:{mode}"}])
    rows.append([{"text": "↩️ Закрыть", "callback_data": CB_SET_CLOSE}])
    return {"inline_keyboard": rows}


async def _team_for_chat(session, chat_id: int):
    return await session.scalar(select(m.TeamModel).where(m.TeamModel.tg_chat_id == chat_id))


async def open_settings(session, chat_id: int) -> ActionsResponse:
    team = await _team_for_chat(session, chat_id)
    if team is None:
        return ActionsResponse(actions=[SendMessageAction(
            chat_id=chat_id,
            text="Настройки доступны в чате команды. Сначала привяжите чат: /bind_team КОД.",
        )])
    mode = (team.board_config or {}).get("digest_mode", DEFAULT_MODE)
    return ActionsResponse(actions=[SendMessageAction(
        chat_id=chat_id,
        text=_settings_text(team, mode, require_cardinal_mention(team)),
        reply_markup=_settings_keyboard(mode, require_cardinal_mention(team), autonomous_mode_enabled(team)),
    )])


def is_settings_callback(data: str) -> bool:
    return (
        data.startswith(f"{CB_SET_DIGEST}:")
        or data in (CB_SET_CARDINAL_MENTION, CB_SET_AUTONOMOUS, CB_SET_CLOSE)
    )


async def handle_settings_callback(session, data: str, event) -> ActionsResponse:
    cq = event.callback_query_id
    chat_id = event.message.chat_id
    msg_id = event.message.message_id
    if data == CB_SET_CLOSE:
        return ActionsResponse(actions=[
            AnswerCallbackAction(callback_query_id=cq, text=""),
            EditMessageAction(chat_id=chat_id, message_id=msg_id, text="⚙️ Настройки закрыты."),
        ])
    team = await _team_for_chat(session, chat_id)
    if team is None:
        return ActionsResponse(
            actions=[AnswerCallbackAction(callback_query_id=cq, text="Чат не привязан")]
        )
    cfg = dict(team.board_config or {})
    mode = cfg.get("digest_mode", DEFAULT_MODE)
    if data == CB_SET_CARDINAL_MENTION:
        cfg[CARDINAL_MENTION_SETTING] = not require_cardinal_mention(team)
    elif data == CB_SET_AUTONOMOUS:
        new_autonomous = not autonomous_mode_enabled(team)
        cfg[AUTONOMOUS_MODE_SETTING] = new_autonomous
        # Sync task confirmation flag for the team's Telegram chat
        chat_row = await session.scalar(
            select(m.TelegramChatModel).where(m.TelegramChatModel.telegram_chat_id == chat_id)
        )
        if chat_row is not None:
            chat_row.task_confirmation_required = not new_autonomous
    else:
        mode = data.split(":", 1)[1]
        if mode not in DIGEST_MODES:
            return ActionsResponse(
                actions=[AnswerCallbackAction(callback_query_id=cq, text="Неизвестный режим")]
            )
        cfg["digest_mode"] = mode
    team.board_config = cfg
    await session.commit()
    cardinal_required = require_cardinal_mention(team)
    autonomous = autonomous_mode_enabled(team)
    return ActionsResponse(actions=[
        AnswerCallbackAction(callback_query_id=cq, text="Сохранено"),
        EditMessageAction(
            chat_id=chat_id, message_id=msg_id,
            text=_settings_text(team, mode, cardinal_required),
            reply_markup=_settings_keyboard(mode, cardinal_required, autonomous),
        ),
    ])
