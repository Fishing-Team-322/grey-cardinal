"""Промпты для LLM-экстракции задач."""

# ruff: noqa: E501

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


SEMANTIC_SYSTEM_PROMPT = (
    "Ты semantic parser для русского Telegram-чата команды.\n"
    "\n"
    "Верни только JSON без markdown.\n"
    "\n"
    "Возможные kind:\n"
    "task_candidate, meeting_candidate, daily_report, absence_notice, "
    "status_update, question, noise, unknown.\n"
    "\n"
    "Не создавай задачу из шуток, болтовни, неопределённых фраз и сообщений без "
    "конкретного действия.\n"
    "\n"
    "Если сообщение не содержит конкретного действия, исполнителя, срока, отчёта, "
    "встречи или отсутствия — верни noise или unknown.\n"
    "\n"
    "Все даты и дедлайны интерпретируй в timezone команды, переданном в контексте.\n"
    "\n"
    "Если не уверен — верни unknown, а не task_candidate.\n"
    "\n"
    "Формат ответа (JSON):\n"
    "{\n"
    '  "kind": "<один из kind>",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "task": {"title": str|null, "description": str|null, '
    '"assignee_text": str|null, "deadline": "ISO8601"|null, "priority": '
    '"low|medium|high|critical"} | null,\n'
    '  "meeting": {"title": str|null, "scheduled_at": "ISO8601"|null, '
    '"duration_minutes": int|null} | null,\n'
    '  "daily_report": {"summary": str|null, "detected_status": str|null} | null,\n'
    '  "absence": {"reason": str|null, "starts_at": "ISO8601"|null, '
    '"ends_at": "ISO8601"|null} | null,\n'
    '  "reason": "короткое объяснение"\n'
    "}\n"
    "Заполняй только тот вложенный объект, который соответствует kind; "
    "остальные ставь null."
)


def build_semantic_prompt(
    message_text: str,
    now: datetime,
    timezone: str,
    sender_display_name: str | None = None,
    team_members: list[str] | None = None,
) -> str:
    """Единый промпт semantic-классификатора (используется и в проде, и в eval).

    Контекст содержит team_timezone/now/sender_display_name/team_members, как
    требует ТЗ, чтобы модель верно интерпретировала даты и исполнителей.
    """
    context = {
        "team_timezone": timezone,
        "now": now.isoformat(),
        "sender_display_name": sender_display_name,
        "team_members": team_members or [],
    }
    return (
        f"{SEMANTIC_SYSTEM_PROMPT}\n\n"
        "Контекст (JSON):\n"
        f"{json.dumps(context, ensure_ascii=False)}\n\n"
        "Сообщение для классификации:\n"
        f"{message_text}"
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
