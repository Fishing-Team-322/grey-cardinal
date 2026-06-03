"""Политика «что считать задачей» — чистая бизнес-логика без I/O.

Здесь живут:

* стемы глаголов-поручений и детектор `has_action_verb` (его переиспользует
  эвристический экстрактор в infrastructure);
* `evaluate_task_extraction` — policy-уровень перед созданием proposal,
  отсекающий низкоуверенные/болтливые срабатывания экстрактора.

Слой application зависит только от домена и контрактов, поэтому модуль не
импортирует ничего из infrastructure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from brain_api.application.config import AppConfig
from grey_cardinal_contracts import TaskExtractionResult

# Стемы-индикаторы поручения (без учёта окончаний).
ACTION_VERB_STEMS: tuple[str, ...] = (
    "подготов", "сделай", "сдела", "сделать", "проверь", "провер", "нужно",
    "надо", "должен", "должна", "должны", "добав", "напиш", "написать",
    "исправ", "оформ", "созда", "отправ", "залить", "выложить", "выложи",
    "обнов", "сверст", "почин", "реализ", "запили", "запус", "настро",
    "собери", "собрать", "протестир", "затащи", "доделай", "доделать",
    "закрой", "закрыть", "закры", "реши", "решить", "согласу", "подпиш",
)

# Слова, которые внешне похожи на стем, но задачей не являются.
NON_TASK_INDICATOR_WORDS: frozenset[str] = frozenset(
    {"настроение", "настроения", "настроением", "настроению"}
)


def has_action_verb(text: str) -> bool:
    """Есть ли в тексте глагол-поручение (надо/сделать/подготовь/...)."""
    lowered = text.lower()
    for stem in ACTION_VERB_STEMS:
        pattern = rf"\b{re.escape(stem)}[\w-]*"
        for match in re.finditer(pattern, lowered):
            if match.group(0) not in NON_TASK_INDICATOR_WORDS:
                return True
    return False


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Решение policy-слоя: создавать proposal или нет, и почему."""

    create_proposal: bool
    reason: str


def evaluate_task_extraction(
    extraction: TaskExtractionResult,
    raw_text: str,
    config: AppConfig,
) -> PolicyDecision:
    """Решить, создавать ли proposal из результата экстрактора.

    Порядок проверок:

    1. Экстрактор вообще не нашёл задачу -> нет proposal.
    2. `TASK_EXTRACTION_REQUIRE_ACTION_VERB`: если нет ни глагола-поручения,
       ни явного исполнителя -> нет proposal (отсекаем «оплата до пятницы»
       без контекста, при этом «Петя, оплата до пятницы» проходит за счёт
       исполнителя).
    3. `confidence < TASK_EXTRACTION_MIN_CONFIDENCE` -> нет proposal (болтовня
       вида «ахаха, надо поспать» имеет низкую уверенность).
    """
    if not extraction.has_task:
        return PolicyDecision(False, "no_task")

    if config.task_extraction_require_action_verb and not has_action_verb(raw_text):
        if not extraction.assignee:
            return PolicyDecision(False, "no_action_verb")

    if extraction.confidence < config.task_extraction_min_confidence:
        return PolicyDecision(False, "low_confidence")

    return PolicyDecision(True, "ok")
