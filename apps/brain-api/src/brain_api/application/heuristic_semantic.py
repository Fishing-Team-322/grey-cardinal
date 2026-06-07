"""Эвристический классификатор сообщений командного чата (без LLM).

Используется как fallback для :class:`SemanticMessageParser`, когда LLM не
настроен или недоступен. Возвращает тот же контракт, что и LLM-парсер
(`kind / confidence / task / meeting / daily_report / absence / reason`), поэтому
маршрутизация в `internal_telegram._try_v2_semantic_message` работает одинаково.

Это намеренно простой rule-based слой: его задача — чтобы бот не «молчал», когда
LLM выключен, и чтобы базовые сценарии (созвон / задача / статус / отсутствие)
можно было прогонять оффлайн.
"""

from __future__ import annotations

import re
from datetime import datetime

from brain_api.application.text_policy import has_action_verb
from brain_api.infrastructure.llm.heuristic_extractor import (
    _USERNAME_RE,
    _extract_assignee,
    _extract_deadline,
)

# Сильные сигналы созвона — само слово уже почти гарантирует встречу.
_MEETING_STRONG = (
    "созвон",
    "созвонимся",
    "созвонимc",  # опечатки/раскладка
    "митинг",
    "meeting",
    "планёрк",
    "планерк",
    "дейли",
    "daily",
    "стендап",
    "stand-up",
    "standup",
    "созвонч",
    "конференц",
)
# Слабые сигналы — нужны вместе со временем, чтобы не ловить ложь.
_MEETING_WEAK = ("встреч", "встретим", "колл", "звонок", "созвон")

_STATUS_DONE = ("сделал", "сделала", "готово", "выполнил", "выполнила", "закрыл", "закрыла", "done")
_STATUS_PROGRESS = (
    "в процессе",
    "делаю",
    "занимаюсь",
    "работаю над",
    "взял в работу",
    "взяла в работу",
    "приступил",
    "приступила",
)
_STATUS_BLOCKED = ("блокер", "заблокир", "застрял", "не получается", "жду", "blocked")

_ABSENCE = (
    "не буду",
    "меня не будет",
    "в отпуск",
    "отпуске",
    "болею",
    "на больничн",
    "заболел",
    "уезжаю",
    "отсутств",
    "не смогу прийти",
)

_DURATION_RE = re.compile(r"\b(\d{1,3})\s*(?:мин|min)\b")
_TIME_PRESENT_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b|\b(?:в|к|до)\s+\d{1,2}\b")


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _empty() -> dict:
    return {
        "kind": "noise",
        "confidence": 0.0,
        "task": None,
        "meeting": None,
        "daily_report": None,
        "absence": None,
        "reason": "heuristic: no signal",
    }


def classify_message(
    text: str,
    now: datetime,
    timezone: str,
    known_users: list | None = None,
) -> dict:
    """Классифицировать сообщение чата по контракту semantic_message_v2."""
    known_users = known_users or []
    raw = (text or "").strip()
    if not raw:
        return _empty()
    lowered = raw.lower()

    # 1. Созвон / встреча.
    meeting = _detect_meeting(raw, lowered, now)
    if meeting is not None:
        return meeting

    # 2. Отсутствие («меня не будет», «в отпуске»).
    if any(token in lowered for token in _ABSENCE) and "созвон" not in lowered:
        result = _empty()
        result.update(
            kind="absence_notice",
            confidence=0.7,
            absence={
                "reason": raw[:200],
                "starts_at": _iso(now),
                "ends_at": None,
            },
            reason="heuristic: absence keywords",
        )
        return result

    # 3. Обновление статуса по своим задачам.
    status = _detect_status(lowered)
    if status is not None:
        result = _empty()
        result.update(
            kind="status_update",
            confidence=0.7,
            daily_report={"summary": raw[:200], "detected_status": status},
            reason=f"heuristic: status={status}",
        )
        return result

    # 4. Задача (глагол-поручение или явный адресат).
    task = _detect_task(raw, lowered, now, known_users)
    if task is not None:
        return task

    return _empty()


def _detect_meeting(raw: str, lowered: str, now: datetime) -> dict | None:
    has_strong = any(token in lowered for token in _MEETING_STRONG)
    has_time = bool(_TIME_PRESENT_RE.search(lowered))
    has_weak = any(token in lowered for token in _MEETING_WEAK)

    if not has_strong and not (has_weak and has_time):
        return None

    scheduled_at, _span = _extract_deadline(raw, lowered, now)
    if scheduled_at is None:
        # Созвон без явного времени — всё равно встреча, но менее уверенно.
        scheduled_at = None

    duration = 60
    dmatch = _DURATION_RE.search(lowered)
    if dmatch:
        duration = max(5, min(int(dmatch.group(1)), 480))

    confidence = 0.6
    if has_strong:
        confidence += 0.1
    if scheduled_at is not None:
        confidence += 0.15
    confidence = round(min(confidence, 0.95), 2)

    result = _empty()
    result.update(
        kind="meeting_candidate",
        confidence=confidence,
        meeting={
            "title": "Созвон",
            "scheduled_at": _iso(scheduled_at),
            "duration_minutes": duration,
        },
        reason="heuristic: meeting keywords",
    )
    return result


def _detect_status(lowered: str) -> str | None:
    if any(token in lowered for token in _STATUS_BLOCKED):
        return "blocked"
    if any(token in lowered for token in _STATUS_DONE):
        return "done"
    if any(token in lowered for token in _STATUS_PROGRESS):
        return "in_progress"
    return None


# Имя — всегда с заглавной (без IGNORECASE, иначе ловит «привет всем»).
_EY_NAME_RE = re.compile(r"^\s*(?:[Ээ]й|[Сс]лушай|[Хх]ей)[\s,]+([А-ЯЁ][а-яё]{2,})")
_NAME_TEBE_RE = re.compile(r"\b([А-ЯЁ][а-яё]{2,})\s*,?\s+(?:тебе|тебя)\b")


def _detect_task(
    raw: str, lowered: str, now: datetime, known_users: list
) -> dict | None:
    username = _USERNAME_RE.search(raw)
    assignee = _extract_assignee(raw, lowered, username, known_users)
    # Доп. паттерны исполнителя: «Эй Саня …», «Саня тебе надо …».
    if assignee is None:
        m = _EY_NAME_RE.match(raw) or _NAME_TEBE_RE.search(raw)
        if m:
            assignee = m.group(1)
    has_verb = has_action_verb(raw)
    if not has_verb and assignee is None:
        return None

    deadline, _span = _extract_deadline(raw, lowered, now)
    priority = "high" if any(
        p in lowered for p in ("срочно", "asap", "критич", "немедленно", "горит")
    ) else "medium"

    confidence = 0.5
    if deadline is not None:
        confidence += 0.2
    if assignee is not None:
        confidence += 0.2
    if has_verb:
        confidence += 0.1
    confidence = round(min(confidence, 0.95), 2)

    result = _empty()
    result.update(
        kind="task_candidate",
        confidence=confidence,
        task={
            "title": raw[:120],
            "description": None,
            "assignee_text": assignee,
            "deadline": _iso(deadline),
            "priority": priority,
        },
        reason="heuristic: action verb / assignee",
    )
    return result
