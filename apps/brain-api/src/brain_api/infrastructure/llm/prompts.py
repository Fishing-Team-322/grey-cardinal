"""Промпты для LLM-экстракции задач."""

from __future__ import annotations

import json
from datetime import datetime

from grey_cardinal_contracts import KnownUser

SYSTEM_PROMPT = (
    "Ты — ассистент проджект-менеджера. Из сообщения команды в чате ты извлекаешь "
    "ровно одну задачу, если она есть. Отвечай СТРОГО валидным JSON без markdown.\n"
    "Схема ответа:\n"
    "{\n"
    '  "has_task": bool,\n'
    '  "title": "краткая формулировка задачи в инфинитиве или null",\n'
    '  "description": "уточнение или null",\n'
    '  "assignee": "имя/username ответственного или null",\n'
    '  "deadline": "ISO8601 с таймзоной или null",\n'
    '  "priority": "low|medium|high|critical",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "reason": "короткое объяснение"\n'
    "}\n"
    "Если поручения нет — верни has_task=false. Дедлайн вычисляй относительно "
    "переданного текущего времени и таймзоны."
)


def build_user_prompt(
    text: str,
    now: datetime,
    timezone: str,
    known_users: list[KnownUser],
) -> str:
    users = [{"name": u.display_name, "username": u.telegram_username} for u in known_users]
    context = {
        "now": now.isoformat(),
        "timezone": timezone,
        "known_users": users,
        "message": text,
    }
    return (
        "Контекст и сообщение (JSON):\n"
        + json.dumps(context, ensure_ascii=False)
        + "\nИзвлеки задачу согласно схеме."
    )
