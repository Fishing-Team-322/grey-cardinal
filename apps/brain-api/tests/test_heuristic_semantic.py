"""Тесты эвристического fallback-классификатора сообщений (без LLM)."""

from datetime import UTC, datetime

import pytest

from brain_api.application.heuristic_semantic import classify_message

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "text",
    [
        "А давайте созвон в 18:00?",
        "В 21:00 будет созвон, приходите все",
        "Митинг завтра в 15:30",
        "Созвонимся сегодня в 19",
    ],
)
def test_detects_meeting(text):
    result = classify_message(text, NOW, "Europe/Moscow")
    assert result["kind"] == "meeting_candidate"
    assert result["confidence"] >= 0.6
    assert result["meeting"] is not None


def test_meeting_extracts_time():
    result = classify_message("Давайте созвон в 18:00", NOW, "Europe/Moscow")
    assert result["meeting"]["scheduled_at"] is not None
    assert "18:00" in result["meeting"]["scheduled_at"]


def test_detects_task_with_assignee_and_deadline():
    result = classify_message("Петя, подготовь оплату завтра до 18:00", NOW, "Europe/Moscow")
    assert result["kind"] == "task_candidate"
    assert result["confidence"] >= 0.65
    assert result["task"]["deadline"] is not None


def test_detects_task_ey_name():
    text = "Эй Саня тебе надо клавиатуру собрать до вечера"
    result = classify_message(text, NOW, "Europe/Moscow")
    assert result["kind"] == "task_candidate"
    assert result["task"]["assignee_text"] == "Саня"


def test_detects_status_done():
    result = classify_message("Я сделал задачу по авторизации", NOW, "Europe/Moscow")
    assert result["kind"] == "status_update"
    assert result["daily_report"]["detected_status"] == "done"


def test_detects_status_blocked():
    result = classify_message("Застрял, жду доступы — блокер", NOW, "Europe/Moscow")
    assert result["kind"] == "status_update"
    assert result["daily_report"]["detected_status"] == "blocked"


def test_detects_absence():
    result = classify_message("Завтра меня не будет, уезжаю", NOW, "Europe/Moscow")
    assert result["kind"] == "absence_notice"
    assert result["absence"] is not None


def test_smalltalk_is_noise():
    result = classify_message("привет всем, как дела?", NOW, "Europe/Moscow")
    assert result["kind"] == "noise"
    assert result["confidence"] == 0.0
