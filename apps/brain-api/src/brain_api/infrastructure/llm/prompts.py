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
    "Ты аккуратный semantic parser для русского Telegram-чата рабочей команды.\n"
    "\n"
    "Верни только JSON без markdown.\n"
    "\n"
    "Возможные kind:\n"
    "task_candidate, task_reassignment, task_cancellation, meeting_candidate, "
    "daily_report, absence_notice, status_update, question, noise, unknown.\n"
    "\n"
    "task_reassignment — переброс СУЩЕСТВУЮЩЕЙ задачи на другого исполнителя: "
    "«Задачу по X будет делать Кирилл», «Я буду делать задачу по X», "
    "«переназначь GC-17 на Аню», «пусть Аня этим займётся». Заполни reassignment: "
    "{task_reference (как названа задача: 'GC-17' или 'по автоматизации API'), "
    "new_assignee_reference (имя/username нового исполнителя; если автор берёт на себя — "
    "его собственное имя), new_assignee_reference_type}. Это НЕ создание новой задачи.\n"
    "task_cancellation — отмена/закрытие существующей задачи как ненужной: "
    "«эта задача по X неактуальна», «GC-17 неактуальна», «отмени задачу по X», "
    "«закрой как ненужную». Заполни cancellation: {task_reference}. Это НЕ status_update "
    "(сделано) и НЕ создание задачи.\n"
    "\n"
    "Отделяй рабочее поручение с проверяемым результатом от шутки, ругани, "
    "болтовни, подтверждения, благодарности и неопределённой фразы.\n"
    "Грубая лексика сама по себе не запрещает задачу, если есть конкретный "
    "рабочий результат. Оскорбление без результата задачей не является.\n"
    "Фразы вроде 'сделай задачу', 'complete the task', 'сделай это' без reply-"
    "контекста являются vague и не должны создавать proposal.\n"
    "\n"
    "Если сообщение не содержит конкретного действия, исполнителя, срока, отчёта, "
    "встречи или отсутствия — верни noise или unknown.\n"
    "\n"
    "Все даты и дедлайны интерпретируй в timezone команды, переданном в контексте.\n"
    "\n"
    "Если не уверен — снижай confidence и should_create_proposal, не выдумывай "
    "исполнителя или объект действия.\n"
    "Исполнителя не сопоставляй с пользователем. Верни только буквальную ссылку "
    "из текста: assignee_reference='Денису', type='name'. Backend выполнит resolve.\n"
    "\n"
    "Формат ответа (JSON):\n"
    "{\n"
    '  "kind": "<один из kind>",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "business_relevance": 0.0-1.0,\n'
    '  "is_actionable": bool,\n'
    '  "is_abusive": bool,\n'
    '  "is_vague": bool,\n'
    '  "should_create_proposal": bool,\n'
    '  "task": {"title": str|null, "description": str|null, '
    '"action_object": str|null, "assignee_text": str|null, '
    '"assignee_reference": str|null, '
    '"assignee_reference_type": "name|username|pronoun|none", '
    '"deadline": "ISO8601"|null, "priority": '
    '"low|medium|high|critical"} | null,\n'
    '  "meeting": {"title": str|null, "scheduled_at": "ISO8601"|null, '
    '"duration_minutes": int|null} | null,\n'
    '  "daily_report": {"summary": str|null, "detected_status": str|null} | null,\n'
    '  "absence": {"reason": str|null, "starts_at": "ISO8601"|null, '
    '"ends_at": "ISO8601"|null} | null,\n'
    '  "reassignment": {"task_reference": str|null, "new_assignee_reference": str|null, '
    '"new_assignee_reference_type": "name|username|pronoun|none"} | null,\n'
    '  "cancellation": {"task_reference": str|null} | null,\n'
    '  "affect": {"valence": -1.0..1.0, "stress": 0.0..1.0, '
    '"dominant_emotion": str|null},\n'
    '  "reason": "короткое объяснение"\n'
    "}\n"
    "Заполняй только тот вложенный объект, который соответствует kind; "
    "остальные ставь null.\n"
    "affect заполняй ВСЕГДА — это эмоциональная окраска сообщения: valence "
    "(−1 негатив … +1 позитив), stress (0 спокойно … 1 сильный стресс/раздражение), "
    "dominant_emotion (радость/спокойствие/усталость/раздражение/тревога и т.п.)."
)


def build_semantic_prompt(
    message_text: str,
    now: datetime,
    timezone: str,
    sender_display_name: str | None = None,
    team_members: list[str] | None = None,
    interaction_mode: str = "AUTO_BACKGROUND",
    reply_to_text: str | None = None,
    reply_to_sender_display_name: str | None = None,
    recent_messages: list[dict] | None = None,
) -> str:
    """Единый промпт semantic-классификатора (используется и в проде, и в eval).

    Контекст содержит team_timezone/now/sender_display_name/team_members, как
    требует ТЗ, чтобы модель верно интерпретировала даты и исполнителей.
    ``recent_messages`` — недавняя переписка чата (скользящее окно) для разрешения
    местоимений («сделай это», «эта задача») и ссылок на задачи без явного GC-N.
    """
    context = {
        "team_timezone": timezone,
        "now": now.isoformat(),
        "sender_display_name": sender_display_name,
        "team_members": team_members or [],
        "interaction_mode": interaction_mode,
        "reply_to": {
            "text": reply_to_text,
            "sender_display_name": reply_to_sender_display_name,
        }
        if reply_to_text or reply_to_sender_display_name
        else None,
    }
    if recent_messages:
        context["conversation"] = recent_messages
    suffix = (
        "Используй conversation как контекст для разрешения местоимений и ссылок "
        "на задачи, но классифицируй ИМЕННО последнее сообщение ниже.\n\n"
        if recent_messages
        else ""
    )
    return (
        f"{SEMANTIC_SYSTEM_PROMPT}\n\n"
        "Контекст (JSON):\n"
        f"{json.dumps(context, ensure_ascii=False)}\n\n"
        f"{suffix}"
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
