"""Промпты для LLM-экстракции задач."""

from __future__ import annotations

import json
from datetime import datetime

from grey_cardinal_contracts import KnownUser

SYSTEM_PROMPT = (
    "Ты — ассистент проджект-менеджера. Анализируешь реплику или фрагмент диалога команды "
    "и извлекаешь ровно одну задачу, если она есть.\n"
    "Важные правила:\n"
    "- 'Сделаю', 'Возьму', 'Окей, берусь' в ответ на поручение = принятая задача для этого участника.\n"
    "- Если участник отвечает согласием на реплику другого — исполнитель тот, кто согласился.\n"
    "- Если диалог дан как контекст — фокусируйся на последней реплике, используй контекст для уточнения.\n"
    "Отвечай СТРОГО валидным JSON без markdown:\n"
    "{\n"
    '  "has_task": bool,\n'
    '  "title": "краткая задача в инфинитиве или null",\n'
    '  "description": "уточнение или null",\n'
    '  "assignee": "имя/username исполнителя или null",\n'
    '  "deadline": "ISO8601 или null",\n'
    '  "priority": "low|medium|high|critical",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "reason": "короткое объяснение"\n'
    "}\n"
    "Если поручения нет — has_task=false. Дедлайн вычисляй от текущего времени."
)


def build_user_prompt(
    text: str,
    now: datetime,
    timezone: str,
    known_users: list[KnownUser],
    conversation_context: str | None = None,
) -> str:
    users = [{"name": u.display_name, "username": u.telegram_username} for u in known_users]
    payload: dict = {
        "now": now.isoformat(),
        "timezone": timezone,
        "known_users": users,
    }
    if conversation_context:
        payload["conversation_context"] = conversation_context
        payload["last_message"] = text
    else:
        payload["message"] = text

    suffix = "Извлеки задачу из последней реплики, используя контекст диалога." if conversation_context else "Извлеки задачу согласно схеме."
    return (
        "Данные (JSON):\n"
        + json.dumps(payload, ensure_ascii=False)
        + f"\n{suffix}"
    )
