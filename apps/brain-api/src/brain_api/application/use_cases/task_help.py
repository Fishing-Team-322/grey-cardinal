"""«Помощь по задаче»: бот отдаёт ссылки на материалы (YouTube / статьи / поиск).

Сотрудник, не знающий как сделать задачу, пишет боту `/help <тема>` (или нажимает
кнопку «🔎 Материалы»), и бот возвращает набор кликабельных ссылок-поисков по теме.
Без внешних API-ключей — формируем URL'ы поисковой выдачи (мгновенно).
"""

from __future__ import annotations

import html as _html
import re
import urllib.parse
from uuid import UUID

from sqlalchemy import select

from brain_api.infrastructure.db import models as m
from grey_cardinal_contracts import ActionsResponse, AnswerCallbackAction, SendMessageAction

CB_HELP_TASK = "help_task"  # help_task:<task_id>

# слова-обёртки, которые отрезаем, чтобы получить чистую тему запроса
_STRIP_PREFIXES = (
    "помощь по задаче", "помощь", "материалы по задаче", "материалы",
    "как сделать", "как ", "помоги с", "помоги",
)


def clean_topic(text: str) -> str:
    t = (text or "").strip()
    low = t.lower()
    for p in _STRIP_PREFIXES:
        if low.startswith(p):
            t = t[len(p):].strip(" :,-—")
            break
    return t or text.strip()


def build_materials(topic: str) -> str:
    """HTML-сообщение с кликабельными ссылками, замаскированными под текст."""
    q = topic.strip()
    enc = urllib.parse.quote_plus(q)
    safe = _html.escape(q)
    return (
        "🔎 <b>Материалы по задаче</b>\n\n"
        f"«{safe}»\n\n"
        f'▶️ <a href="https://www.youtube.com/results?search_query={enc}">YouTube — видео</a>\n'
        f'📚 <a href="https://habr.com/ru/search/?q={enc}">Хабр — статьи</a>\n'
        f'💬 <a href="https://stackoverflow.com/search?q={enc}">StackOverflow</a>\n'
        f'📰 <a href="https://dev.to/search?q={enc}">dev.to</a>\n'
        f'🔍 <a href="https://www.google.com/search?q={enc}">Google</a>\n\n'
        "Жми ссылки — там видео и статьи по теме."
    )


def _gc_id(text: str) -> str | None:
    match = re.search(r"GC-\d+", text or "", flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


async def materials_for_arg(session, arg: str) -> str:
    """arg может быть GC-id (берём заголовок задачи) или произвольной темой."""
    gid = _gc_id(arg)
    if gid:
        task = await session.scalar(select(m.TaskModel).where(m.TaskModel.public_id == gid))
        if task is not None:
            return build_materials(task.title)
    return build_materials(clean_topic(arg))


def is_help_callback(data: str) -> bool:
    return data.startswith(f"{CB_HELP_TASK}:")


async def handle_help_callback(session, data: str, event) -> ActionsResponse:
    _action, _, raw_id = data.partition(":")
    cq = event.callback_query_id
    try:
        task_id = UUID(raw_id)
    except ValueError:
        return ActionsResponse(
            actions=[AnswerCallbackAction(callback_query_id=cq, text="Нет задачи")]
        )
    task = await session.get(m.TaskModel, task_id)
    if task is None:
        return ActionsResponse(
            actions=[AnswerCallbackAction(callback_query_id=cq, text="Задача не найдена")]
        )
    return ActionsResponse(actions=[
        AnswerCallbackAction(callback_query_id=cq, text="Материалы ниже"),
        SendMessageAction(
            chat_id=event.message.chat_id, text=build_materials(task.title), parse_mode="HTML"
        ),
    ])


def is_help_request_text(text: str) -> bool:
    low = (text or "").strip().lower()
    return low.startswith(("помощь", "материал", "как сделать", "помоги"))
