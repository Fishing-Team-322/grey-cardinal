"""Rule-based task extractor (Russian) — honest fallback, no LLM required.

This is NOT a fake extractor: it only reports has_task=True when the text
contains a real action verb / task indicator. It extracts title, assignee,
deadline phrase, description and a confidence score.

If an LLM is configured later, it can be plugged in front of this as a
higher-priority extractor; this stays as the deterministic fallback.

Handles the demo examples:
    "Нужно оплатить сервер до четверга, ответственный Иван"
    "Денис, сделай лендинг завтра"
    "Маша подготовит отчёт к пятнице"
    "надо обновить README сегодня"
    "поставь задачу Пете проверить API до вечера"
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #

# Action-verb stems (lowercased). Presence of any → text describes a task.
_VERB_STEMS = (
    "сдела",
    "сдел",  # сделай / сделать / сделает
    "подготов",  # подготовь / подготовить / подготовит
    "провер",  # проверь / проверить / проверит
    "оплат",  # оплати / оплатить / оплатит
    "обнов",  # обнови / обновить / обновит
    "созда",  # создай / создать
    "добав",  # добавь / добавить
    "исправ",  # исправь / исправить
    "постав",  # поставь / поставить
    "напиш",
    "напис",  # напиши / написать
    "отправ",  # отправь / отправить
    "запус",  # запусти / запустить
    "настро",  # настрой / настроить
    "подключ",  # подключи / подключить
    "разверн",  # разверни / развернуть
    "почин",  # почини / починить
    "согласу",  # согласуй / согласовать
)

# Standalone task indicator words.
_INDICATORS = ("надо", "нужно", "необходимо", "требуется")

_PRIORITY_HIGH = ("срочно", "asap", "критич", "немедленно", "горит", "сегодня же")

_USERNAME_RE = re.compile(r"@([A-Za-z0-9_]{2,})")
_NAME = r"[А-ЯЁ][а-яё]+"

# Deadline phrases — ordered, first match wins. Each entry: (regex, label builder).
_DEADLINE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bпослезавтра\b", re.IGNORECASE),
    re.compile(r"\bзавтра\b", re.IGNORECASE),
    re.compile(r"\bсегодня\b", re.IGNORECASE),
    re.compile(r"\b(?:до|к)\s+вечер\w*\b", re.IGNORECASE),
    re.compile(r"\bдо\s+утр\w*\b", re.IGNORECASE),
    re.compile(r"\bна\s+недел\w*\b", re.IGNORECASE),
    re.compile(
        r"\b(?:до|к|в|во)\s+"
        r"(?:понедельник\w*|вторник\w*|сред\w*|четверг\w*|пятниц\w*|суббот\w*|воскресен\w*)\b",
        re.IGNORECASE,
    ),
    # Bare weekday without preposition (e.g. "в пятницу" handled above; this catches "пятница").
    re.compile(
        r"\b(?:понедельник\w*|вторник\w*|четверг\w*|пятниц\w*|суббот\w*|воскресен\w*)\b",
        re.IGNORECASE,
    ),
]


@dataclass
class Extracted:
    has_task: bool
    title: str = ""
    assignee: str = ""
    deadline: str = ""
    description: str = ""
    source: str = "chat"
    confidence: float = 0.0
    reason: str = ""


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def extract_task(text: str, *, author: str = "", source: str = "chat") -> Extracted:
    """Extract a task proposal from free Russian text.

    Returns Extracted(has_task=False) when no action verb / indicator is found.
    """
    raw = (text or "").strip()
    if not raw:
        return Extracted(has_task=False, source=source, reason="empty text")

    lowered = raw.lower()

    has_verb = any(stem in lowered for stem in _VERB_STEMS)
    has_indicator = any(ind in lowered for ind in _INDICATORS)

    if not has_verb and not has_indicator:
        return Extracted(has_task=False, source=source, reason="no action verb / indicator")

    assignee = _extract_assignee(raw, lowered, author)
    deadline = _extract_deadline(raw)
    title = _build_title(raw, assignee, deadline)
    description = _build_description(raw)

    confidence = 0.5
    if deadline:
        confidence += 0.2
    if assignee and assignee != author:
        confidence += 0.2
    if has_verb:
        confidence += 0.1
    confidence = round(min(confidence, 0.95), 2)

    priority = "high" if any(p in lowered for p in _PRIORITY_HIGH) else "medium"

    return Extracted(
        has_task=True,
        title=title or raw[:120],
        assignee=assignee,
        deadline=deadline,
        description=description,
        source=source,
        confidence=confidence,
        reason=f"rule-based: verb={has_verb} indicator={has_indicator} priority={priority}",
    )


# --------------------------------------------------------------------------- #
# Assignee
# --------------------------------------------------------------------------- #


def _extract_assignee(text: str, lowered: str, author: str) -> str:
    # 1. "ответственный/ответственная <Имя>" (optionally with colon).
    m = re.search(rf"ответственн\w*\s*:?\s*(@?{_NAME}|@[A-Za-z0-9_]+)", text)
    if m:
        return m.group(1)

    # 2. @username.
    um = _USERNAME_RE.search(text)
    if um:
        return "@" + um.group(1)

    # 3. "задачу <Имя>" — e.g. "поставь задачу Пете проверить API".
    m = re.search(rf"задач\w*\s+({_NAME})", text)
    if m:
        return m.group(1)

    # 4. Leading "Имя, ..." — e.g. "Денис, сделай лендинг".
    head = text.lstrip()
    comma = head.find(",")
    if 0 < comma <= 24:
        candidate = head[:comma].strip()
        if re.fullmatch(_NAME, candidate):
            return candidate

    # 5. "Имя должен/должна/должны ...".
    m = re.search(rf"\b({_NAME})\s+должн[аыо]?\b", text)
    if m:
        return m.group(1)

    # 6. "Имя <action-verb>" — capitalized name immediately before a verb.
    #    e.g. "Маша подготовит отчёт", "Денис сделает".
    m = re.search(rf"\b({_NAME})\s+(\w+)", text)
    if m and any(m.group(2).lower().startswith(stem) for stem in _VERB_STEMS):
        return m.group(1)

    # 7. Fallback: the message author.
    return author or ""


# --------------------------------------------------------------------------- #
# Deadline
# --------------------------------------------------------------------------- #


def _extract_deadline(text: str) -> str:
    for pattern in _DEADLINE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0).strip()
    return ""


# --------------------------------------------------------------------------- #
# Title / description
# --------------------------------------------------------------------------- #


def _build_title(text: str, assignee: str, deadline: str) -> str:
    result = text.strip()

    # Remove @username tokens.
    result = _USERNAME_RE.sub("", result)

    # Remove "ответственный <Имя>" clause (with optional leading comma).
    result = re.sub(rf",?\s*ответственн\w*\s*:?\s*(?:@?{_NAME}|@[A-Za-z0-9_]+)", "", result)

    # Remove leading filler indicators.
    result = re.sub(
        r"^(нужно|надо|необходимо|требуется|пожалуйста)\s+", "", result, flags=re.IGNORECASE
    )

    # Remove leading "поставь задачу <Имя>".
    result = re.sub(rf"^постав\w*\s+задач\w*\s+{_NAME}\s+", "", result, flags=re.IGNORECASE)

    # Remove leading "<assignee>," or "<assignee> должен/должна".
    if assignee and not assignee.startswith("@"):
        esc = re.escape(assignee)
        result = re.sub(rf"^{esc}\s*,\s*", "", result)
        result = re.sub(rf"^{esc}\s+должн[аыо]?\s+", "", result)
        result = re.sub(rf"^{esc}\s+", "", result)

    # Remove deadline phrase wherever it appears.
    if deadline:
        result = result.replace(deadline, "")

    # Collapse whitespace, strip punctuation.
    result = re.sub(r"\s+", " ", result).strip(" ,.;:—-")

    if result:
        result = result[0].upper() + result[1:]
    return result


def _build_description(text: str) -> str:
    # Honest description: the original text minus a trailing "ответственный X" clause.
    result = re.sub(
        rf",?\s*ответственн\w*\s*:?\s*(?:@?{_NAME}|@[A-Za-z0-9_]+)\s*$", "", text.strip()
    )
    return result.strip(" ,.;")
