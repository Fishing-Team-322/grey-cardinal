"""Эвристический экстрактор задач (русский язык).

Работает без LLM и используется по умолчанию, когда LLM_API_KEY пуст. Понимает
типичные поручения вида:

    Петя, подготовь макет главного экрана до завтра 18:00
    @petya сделай API авторизации до 18:00
    Маша должна проверить оплату сегодня
    Нужно подготовить презентацию к пятнице
    Сделать README до завтра
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from grey_cardinal_contracts import KnownUser, TaskExtractionResult, TaskPriority

# Стемы-индикаторы поручения (без учёта окончаний).
_TASK_STEMS = (
    "подготов", "сделай", "сдела", "сделать", "проверь", "провер", "нужно",
    "надо", "должен", "должна", "должны", "добав", "напиш", "написать",
    "исправ", "оформ", "созда", "отправ", "залить", "выложить", "выложи",
    "обнов", "сверст", "почин", "реализ", "запили", "запус", "настро",
    "собери", "собрать", "протестир", "затащи", "доделай", "доделать",
)

_PRIORITY_HIGH = ("срочно", "asap", "критич", "немедленно", "горит")

_WEEKDAYS = {
    "понедельник": 0, "понедельн": 0,
    "вторник": 1,
    "сред": 2,  # среду / среда
    "четверг": 3,
    "пятниц": 4,  # пятницу / пятнице / пятница
    "суббот": 5,
    "воскресен": 6,
}

_TIME_RE = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
_HOUR_ONLY_RE = re.compile(r"\b(?:до|в|к)\s+(\d{1,2})\s*(?:час\w*|ч)?\b")
_USERNAME_RE = re.compile(r"@([A-Za-z0-9_]{3,})")

_DEFAULT_HOUR = 18
_DEFAULT_MINUTE = 0


class HeuristicTaskExtractor:
    """Реализация порта TaskExtractor без LLM."""

    async def extract_task(
        self,
        text: str,
        now: datetime,
        timezone: str,
        known_users: list[KnownUser],
    ) -> TaskExtractionResult:
        lowered = text.lower()

        has_indicator = any(stem in lowered for stem in _TASK_STEMS)
        username = _USERNAME_RE.search(text)
        assignee = _extract_assignee(text, lowered, username, known_users)

        # Нет ни глагола-поручения, ни явного адресата -> это не задача.
        if not has_indicator and assignee is None:
            return TaskExtractionResult(has_task=False, reason="Нет явного поручения")

        deadline, deadline_span = _extract_deadline(text, lowered, now)
        priority = (
            TaskPriority.high if any(p in lowered for p in _PRIORITY_HIGH) else TaskPriority.medium
        )
        title = _build_title(text, assignee, username, deadline_span)

        confidence = 0.5
        if deadline is not None:
            confidence += 0.2
        if assignee is not None:
            confidence += 0.2
        if has_indicator:
            confidence += 0.1
        confidence = round(min(confidence, 0.95), 2)

        return TaskExtractionResult(
            has_task=True,
            title=title or text.strip()[:120],
            description=None,
            assignee=assignee,
            deadline=deadline,
            priority=priority,
            confidence=confidence,
            reason="Эвристика: найден глагол-поручение/адресат",
        )


# --------------------------------------------------------------------------- #
# Вспомогательные функции
# --------------------------------------------------------------------------- #
def _extract_assignee(
    text: str,
    lowered: str,
    username: re.Match[str] | None,
    known_users: list[KnownUser],
) -> str | None:
    if username is not None:
        return "@" + username.group(1)

    # «Имя, ...» в начале сообщения.
    head = text.strip()
    comma = head.find(",")
    if 0 < comma <= 24:
        candidate = head[:comma].strip()
        if candidate and candidate[0].isupper() and " " not in candidate:
            return candidate

    # «Имя должен/должна ...»
    duty = re.search(r"\b([А-ЯЁ][а-яё]+)\s+должн[аы]?\b", text)
    if duty:
        return duty.group(1)

    # Совпадение с известными участниками чата.
    for user in known_users:
        if user.telegram_username and user.telegram_username.lower() in lowered:
            return user.display_name
        if user.display_name and user.display_name.lower() in lowered:
            return user.display_name
    return None


def _extract_deadline(
    text: str, lowered: str, now: datetime
) -> tuple[datetime | None, tuple[int, int] | None]:
    """Вернуть (deadline, (start,end) индексов фразы дедлайна для очистки заголовка)."""
    target_date = None
    span: tuple[int, int] | None = None

    def mark(idx: int, length: int) -> None:
        nonlocal span
        if idx >= 0:
            span = (idx, idx + length)

    if "послезавтра" in lowered:
        target_date = (now + timedelta(days=2)).date()
        mark(lowered.find("послезавтра"), len("послезавтра"))
    elif "завтра" in lowered:
        target_date = (now + timedelta(days=1)).date()
        mark(lowered.find("завтра"), len("завтра"))
    elif "сегодня" in lowered:
        target_date = now.date()
        mark(lowered.find("сегодня"), len("сегодня"))
    else:
        for stem, weekday in _WEEKDAYS.items():
            idx = lowered.find(stem)
            if idx != -1:
                target_date = _next_weekday(now, weekday).date()
                mark(idx, len(stem))
                break

    # Время.
    hour, minute = None, None
    time_match = _TIME_RE.search(text)
    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        if span is None:
            mark(time_match.start(), time_match.end() - time_match.start())
    else:
        hour_match = _HOUR_ONLY_RE.search(lowered)
        if hour_match and target_date is not None:
            hour, minute = int(hour_match.group(1)), 0

    if target_date is None and hour is None:
        return None, None

    if target_date is None:
        target_date = now.date()
    if hour is None:
        hour, minute = _DEFAULT_HOUR, _DEFAULT_MINUTE

    deadline = datetime(
        target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=now.tzinfo
    )
    return deadline, span


def _next_weekday(now: datetime, weekday: int) -> datetime:
    days_ahead = (weekday - now.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return now + timedelta(days=days_ahead)


def _build_title(
    text: str,
    assignee: str | None,
    username: re.Match[str] | None,
    deadline_span: tuple[int, int] | None,
) -> str:
    result = text.strip()

    # Убрать «@username».
    result = _USERNAME_RE.sub("", result).strip()

    # Убрать ведущее «Имя,».
    if assignee and not assignee.startswith("@"):
        result = re.sub(rf"^{re.escape(assignee)}\s*,?\s*", "", result).strip()
        result = re.sub(rf"^{re.escape(assignee)}\s+должн[аы]?\s+", "", result).strip()

    # Убрать хвост-дедлайн (фразу «до завтра 18:00», «к пятнице» и т.п.).
    result = re.sub(
        r"\s*(до|к|в)?\s*(сегодня|завтра|послезавтра|"
        r"понедельник\w*|вторник\w*|сред\w*|четверг\w*|пятниц\w*|суббот\w*|воскресен\w*)?"
        r"\s*\d{0,2}[:.]?\d{0,2}\s*$",
        "",
        result,
    ).strip()

    # Убрать ведущие «нужно/надо».
    result = re.sub(r"^(нужно|надо)\s+", "", result, flags=re.IGNORECASE).strip()
    result = result.strip(" ,.;—-")

    if result:
        result = result[0].upper() + result[1:]
    return result
