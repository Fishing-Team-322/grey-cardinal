"""Fallback включается на сбой primary и НЕ включается на валидный noise/unknown."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from llm_fakes import FakeFactory, FakeProvider

from brain_api.application.semantic_parser import SemanticMessageInput, SemanticMessageParser
from brain_api.infrastructure.llm.errors import (
    LLMInvalidJSONError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
    LLMUnavailableError,
)

TASK_RESPONSE = {
    "kind": "task_candidate",
    "confidence": 0.9,
    "task": {"title": "Подготовить оплату"},
}
NOISE_RESPONSE = {"kind": "noise", "confidence": 0.95, "reason": "болтовня"}


def _payload(text: str) -> SemanticMessageInput:
    return SemanticMessageInput(
        team_id=uuid4(),
        message_text=text,
        sender_user_id=uuid4(),
        team_timezone="Europe/Moscow",
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    "primary_error",
    [
        LLMTimeoutError("timeout"),
        LLMRateLimitError("429"),
        LLMServerError("500"),
        LLMUnavailableError("conn refused"),
        LLMInvalidJSONError("garbage"),
    ],
)
@pytest.mark.asyncio
async def test_fallback_triggers_on_primary_failure(primary_error) -> None:
    primary = FakeProvider([primary_error], max_retries=1)
    fallback = FakeProvider([TASK_RESPONSE], max_retries=1)
    parser = SemanticMessageParser(FakeFactory(primary, fallback))

    result = await parser.parse(_payload("Петя, подготовь оплату до четверга"))

    assert result["kind"] == "task_candidate"
    assert primary.calls >= 1  # primary пробовали (с ретраями)
    assert fallback.calls == 1  # fallback вызван один раз и помог


@pytest.mark.asyncio
async def test_valid_noise_does_not_trigger_fallback() -> None:
    primary = FakeProvider([NOISE_RESPONSE], max_retries=1)
    fallback = FakeProvider([TASK_RESPONSE], max_retries=1)
    parser = SemanticMessageParser(FakeFactory(primary, fallback))

    result = await parser.parse(_payload("ну такое себе если честно, не уверен"))

    # валидный noise — это не сбой провайдера, fallback не трогаем
    assert primary.calls == 1
    assert fallback.calls == 0
    assert result["kind"] in {"noise", "unknown"}


@pytest.mark.asyncio
async def test_both_providers_fail_returns_controlled_failure() -> None:
    primary = FakeProvider([LLMTimeoutError("t")], max_retries=1)
    fallback = FakeProvider([LLMServerError("500")], max_retries=1)
    parser = SemanticMessageParser(FakeFactory(primary, fallback))

    result = await parser.parse(_payload("Петя, подготовь оплату до четверга"))

    assert result["kind"] == "semantic_parse_failed"
    assert result["confidence"] == 0.0
    assert result["task"] is None


@pytest.mark.asyncio
async def test_no_fallback_configured_and_primary_fails() -> None:
    primary = FakeProvider([LLMTimeoutError("t")], max_retries=1)
    parser = SemanticMessageParser(FakeFactory(primary, fallback=None))

    result = await parser.parse(_payload("Петя, подготовь оплату до четверга"))

    assert result["kind"] == "semantic_parse_failed"
