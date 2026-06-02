"""Тесты эвристического экстрактора."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from brain_api.infrastructure.llm.heuristic_extractor import HeuristicTaskExtractor

TZ = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 6, 2, 15, 0, tzinfo=TZ)  # вторник


@pytest.fixture
def extractor() -> HeuristicTaskExtractor:
    return HeuristicTaskExtractor()


async def test_finds_task_with_assignee_and_deadline(extractor):
    result = await extractor.extract_task(
        "Петя, подготовь макет главного экрана до завтра 18:00", NOW, "Europe/Moscow", []
    )
    assert result.has_task is True
    assert result.assignee == "Петя"
    assert result.deadline is not None
    assert result.deadline.date() == NOW.date().replace(day=3)
    assert result.deadline.hour == 18
    assert "макет" in (result.title or "").lower()
    assert result.confidence >= 0.8


async def test_no_task_for_small_talk(extractor):
    result = await extractor.extract_task("Всем привет, как настроение?", NOW, "Europe/Moscow", [])
    assert result.has_task is False


async def test_parses_username_and_today(extractor):
    result = await extractor.extract_task(
        "@petya сделай API авторизации до 18:00", NOW, "Europe/Moscow", []
    )
    assert result.has_task is True
    assert result.assignee == "@petya"
    assert result.deadline is not None
    assert result.deadline.date() == NOW.date()
    assert result.deadline.hour == 18


async def test_parses_dolzhna_assignee(extractor):
    result = await extractor.extract_task(
        "Маша должна проверить оплату сегодня", NOW, "Europe/Moscow", []
    )
    assert result.has_task is True
    assert result.assignee == "Маша"
    assert result.deadline is not None
    assert result.deadline.date() == NOW.date()


async def test_parses_weekday_deadline(extractor):
    result = await extractor.extract_task(
        "Нужно подготовить презентацию к пятнице", NOW, "Europe/Moscow", []
    )
    assert result.has_task is True
    # ближайшая пятница после вторника 2026-06-02 -> 2026-06-05
    assert result.deadline is not None
    assert result.deadline.weekday() == 4


async def test_simple_infinitive_task(extractor):
    result = await extractor.extract_task("Сделать README до завтра", NOW, "Europe/Moscow", [])
    assert result.has_task is True
    assert result.deadline is not None
    assert result.deadline.date() == NOW.date().replace(day=3)
