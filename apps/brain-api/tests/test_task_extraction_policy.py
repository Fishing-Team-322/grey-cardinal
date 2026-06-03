"""Тесты policy-слоя извлечения задач (порог уверенности + глагол-поручение).

Проверяем связку HeuristicTaskExtractor + evaluate_task_extraction на наборе
фраз из ТЗ: первые распознаются как задачи, последние не должны создавать
карточку.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from brain_api.application.config import AppConfig
from brain_api.application.text_policy import (
    evaluate_task_extraction,
    has_action_verb,
)
from brain_api.infrastructure.llm.heuristic_extractor import HeuristicTaskExtractor
from grey_cardinal_contracts import TaskExtractionResult

TZ = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 6, 2, 15, 0, tzinfo=TZ)  # вторник

TASK_PHRASES = [
    "надо сделать оплату до четверга",
    "нужно подготовить договор завтра",
    "Петя, оплата до пятницы",
    "@petya проверь интеграцию сегодня",
    "Маша должна закрыть задачу к вечеру",
]

NON_TASK_PHRASES = [
    "Давайте завтра созвонимся",
    "ахаха, надо поспать",
    "надо бы как-нибудь сделать красиво",
]


@pytest.fixture
def extractor() -> HeuristicTaskExtractor:
    return HeuristicTaskExtractor()


@pytest.fixture
def policy_config() -> AppConfig:
    return AppConfig(
        task_extraction_min_confidence=0.65,
        task_extraction_require_action_verb=True,
    )


async def _decide(extractor, config, text):
    extraction = await extractor.extract_task(text, NOW, "Europe/Moscow", [])
    return extraction, evaluate_task_extraction(extraction, text, config)


@pytest.mark.parametrize("text", TASK_PHRASES)
async def test_task_phrases_create_proposal(extractor, policy_config, text):
    extraction, decision = await _decide(extractor, policy_config, text)
    assert extraction.has_task is True
    assert extraction.confidence >= policy_config.task_extraction_min_confidence
    assert decision.create_proposal is True, f"{text!r} should pass policy"


@pytest.mark.parametrize("text", NON_TASK_PHRASES)
async def test_non_task_phrases_are_suppressed(extractor, policy_config, text):
    _, decision = await _decide(extractor, policy_config, text)
    assert decision.create_proposal is False, f"{text!r} must not create a card"


async def test_low_confidence_is_suppressed(policy_config):
    extraction = TaskExtractionResult(
        has_task=True, title="надо поспать", confidence=0.6, reason="heuristic"
    )
    decision = evaluate_task_extraction(extraction, "надо поспать", policy_config)
    assert decision.create_proposal is False
    assert decision.reason == "low_confidence"


async def test_require_action_verb_blocks_verbless_unassigned():
    config = AppConfig(
        task_extraction_min_confidence=0.5,
        task_extraction_require_action_verb=True,
    )
    extraction = TaskExtractionResult(
        has_task=True, title="оплата", assignee=None, confidence=0.9
    )
    decision = evaluate_task_extraction(extraction, "оплата до пятницы", config)
    assert decision.create_proposal is False
    assert decision.reason == "no_action_verb"


async def test_require_action_verb_allows_explicit_assignee():
    config = AppConfig(
        task_extraction_min_confidence=0.5,
        task_extraction_require_action_verb=True,
    )
    extraction = TaskExtractionResult(
        has_task=True, title="оплата", assignee="Петя", confidence=0.9
    )
    decision = evaluate_task_extraction(extraction, "Петя, оплата до пятницы", config)
    assert decision.create_proposal is True


async def test_require_action_verb_can_be_disabled():
    config = AppConfig(
        task_extraction_min_confidence=0.5,
        task_extraction_require_action_verb=False,
    )
    extraction = TaskExtractionResult(
        has_task=True, title="оплата", assignee=None, confidence=0.9
    )
    decision = evaluate_task_extraction(extraction, "оплата до пятницы", config)
    assert decision.create_proposal is True


def test_has_action_verb_detects_commands():
    assert has_action_verb("надо сделать оплату") is True
    assert has_action_verb("Давайте завтра созвонимся") is False
    assert has_action_verb("как настроение?") is False
