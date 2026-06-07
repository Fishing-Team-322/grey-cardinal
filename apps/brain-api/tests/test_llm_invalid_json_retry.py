"""Invalid JSON -> retry, и только потом fallback (см. ТЗ 2.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from llm_fakes import FakeFactory, FakeProvider

from brain_api.application.semantic_parser import SemanticMessageInput, SemanticMessageParser
from brain_api.infrastructure.llm.errors import LLMInvalidJSONError

TASK_RESPONSE = {"kind": "task_candidate", "confidence": 0.9, "task": {"title": "Оплата"}}


def _payload() -> SemanticMessageInput:
    return SemanticMessageInput(
        team_id=uuid4(),
        message_text="Петя, подготовь оплату до четверга",
        sender_user_id=uuid4(),
        team_timezone="Europe/Moscow",
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_invalid_json_then_valid_retry_succeeds_without_fallback() -> None:
    # 1-й ответ — мусор, 2-й — валидный. retry внутри primary должен спасти.
    primary = FakeProvider(
        [LLMInvalidJSONError("garbage"), TASK_RESPONSE], max_retries=2
    )
    fallback = FakeProvider([TASK_RESPONSE], max_retries=1)
    parser = SemanticMessageParser(FakeFactory(primary, fallback))

    result = await parser.parse(_payload())

    assert result["kind"] == "task_candidate"
    assert primary.calls == 2  # один retry
    assert fallback.calls == 0  # fallback не понадобился


@pytest.mark.asyncio
async def test_invalid_json_exhausts_retries_then_fallback() -> None:
    primary = FakeProvider([LLMInvalidJSONError("garbage")], max_retries=1)
    fallback = FakeProvider([TASK_RESPONSE], max_retries=1)
    parser = SemanticMessageParser(FakeFactory(primary, fallback))

    result = await parser.parse(_payload())

    assert result["kind"] == "task_candidate"
    assert primary.calls == 2  # max_retries=1 => 2 попытки
    assert fallback.calls == 1
