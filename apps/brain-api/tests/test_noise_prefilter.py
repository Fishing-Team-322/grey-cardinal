"""Тесты быстрого pre-filter Telegram-шума (без LLM)."""

from __future__ import annotations

import pytest

from brain_api.application.llm.noise_prefilter import NoisePreFilter

prefilter = NoisePreFilter()


@pytest.mark.parametrize(
    "text",
    [
        "ок",
        "окей",
        "принял",
        "понял",
        "спасибо",
        "спс",
        "+",
        "да",
        "нет",
        "👍",
        "😂",
        "🔥",
        "ОК!",
        "  спасибо  ",
        "да понял",
        "ок спс",
        "",
        "   ",
    ],
)
def test_obvious_noise_is_filtered(text: str) -> None:
    result = prefilter.check(text)
    assert result.is_noise is True
    assert result.reason


@pytest.mark.parametrize(
    "text",
    [
        "да, сделаю сегодня",  # принятие задачи -> не шум
        "ок, тогда созвонимся в 18:00",  # есть время
        "Петя, подготовь оплату до четверга",
        "проверил интеграцию, всё готово",
        "я завтра на больничном",
        "давайте завтра созвонимся",
        "понял, начинаю делать лендинг",
        "спасибо, но нужно ещё доработать отчёт",
        "@petya глянь пожалуйста PR",
        "https://example.com/docs",
    ],
)
def test_meaningful_messages_pass_through(text: str) -> None:
    result = prefilter.check(text)
    assert result.is_noise is False


def test_empty_message_is_noise_with_reason() -> None:
    assert prefilter.check(None).reason == "empty"
    assert prefilter.check("").reason == "empty"


def test_emoji_only_is_noise() -> None:
    result = prefilter.check("🔥🔥🔥")
    assert result.is_noise is True
    assert result.reason == "emoji_only"


def test_time_signal_prevents_false_noise() -> None:
    # короткая фраза, но со временем — не шум
    assert prefilter.check("в 18:00").is_noise is False
