"""Strict JSON: ответ валидируется Pydantic-схемой; невалидная схема -> retry/fallback."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from llm_fakes import FakeFactory, FakeProvider
from pydantic import ValidationError

from brain_api.application.llm.schema import (
    SEMANTIC_KINDS,
    SemanticParseResult,
    semantic_json_schema,
)
from brain_api.application.semantic_parser import SemanticMessageInput, SemanticMessageParser

TASK_RESPONSE = {"kind": "task_candidate", "confidence": 0.9, "task": {"title": "Оплата"}}
BAD_KIND = {"kind": "banana", "confidence": 0.5}
BAD_CONFIDENCE = {"kind": "noise", "confidence": 9.0}


def _payload() -> SemanticMessageInput:
    return SemanticMessageInput(
        team_id=uuid4(),
        message_text="Петя, подготовь оплату до четверга",
        sender_user_id=uuid4(),
        team_timezone="Europe/Moscow",
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )


def test_semantic_schema_accepts_valid_payload() -> None:
    result = SemanticParseResult.model_validate(TASK_RESPONSE)
    assert result.kind == "task_candidate"
    assert result.task is not None
    assert result.task.title == "Оплата"


def test_semantic_schema_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        SemanticParseResult.model_validate(BAD_KIND)


def test_semantic_schema_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        SemanticParseResult.model_validate(BAD_CONFIDENCE)


def test_json_schema_lists_all_kinds() -> None:
    schema = semantic_json_schema()
    enum = schema["schema"]["properties"]["kind"]["enum"]
    assert set(enum) == SEMANTIC_KINDS
    assert "kind" in schema["schema"]["required"]


@pytest.mark.asyncio
async def test_schema_error_triggers_retry_then_fallback() -> None:
    # primary всегда отдаёт валидный JSON, но НЕвалидный по схеме -> fallback.
    primary = FakeProvider([BAD_KIND], max_retries=1)
    fallback = FakeProvider([TASK_RESPONSE], max_retries=1)
    parser = SemanticMessageParser(FakeFactory(primary, fallback))

    result = await parser.parse(_payload())

    assert result["kind"] == "task_candidate"
    assert primary.calls == 2  # retry на schema error
    assert fallback.calls == 1
