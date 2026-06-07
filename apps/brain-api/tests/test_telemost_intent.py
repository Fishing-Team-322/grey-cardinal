"""Deterministic call-intent detection for the Telegram → Telemost MVP."""

from __future__ import annotations

import pytest

from brain_api.application.telemost_intent import detect_call_intent

POSITIVE = [
    "нужен созвон",
    "давайте созвонимся",
    "го созвон",
    "го телемост",
    "надо обсудить голосом",
    "созвон по задаче",
    "Коллеги, давайте созвонимся в 18:00",
    "let's hop on telemost",
    "обсудим голосом?",
    "нужен видеозвонок",
]

NEGATIVE = [
    "доброе утро всем",
    "созвучие мнений по дизайну",   # «созв...» but not «созвон»
    "обсудим задачу в чате",        # no voice/call
    "позвони клиенту насчёт оплаты",  # phone call, not a meeting
    "отчёт готов, посмотрите",
    "",
    "когда дедлайн по задаче?",
]


@pytest.mark.parametrize("text", POSITIVE)
def test_detects_call_intent(text: str) -> None:
    assert detect_call_intent(text) is True


@pytest.mark.parametrize("text", NEGATIVE)
def test_ignores_non_call_messages(text: str) -> None:
    assert detect_call_intent(text) is False


def test_none_is_safe() -> None:
    assert detect_call_intent(None) is False
