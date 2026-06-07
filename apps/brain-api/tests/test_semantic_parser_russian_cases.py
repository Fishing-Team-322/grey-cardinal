"""Сквозные русские кейсы semantic-парсера (prefilter + LLM-контракт + роутинг).

LLM подменён детерминированным fake-провайдером (никаких реальных вызовов).
Проверяем, что:
  * очевидный русский Telegram-шум отсекается prefilter'ом БЕЗ вызова LLM;
  * содержательные русские сообщения доходят до LLM и корректно классифицируются;
  * результат приводится к контракту semantic_message_v2.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from llm_fakes import FakeConfig, FakeFactory, FakeProvider

from brain_api.application.semantic_parser import SemanticMessageInput, SemanticMessageParser


class MappedProvider(FakeProvider):
    """Возвращает kind по последней строке промпта (по словарю expected)."""

    def __init__(self, mapping: dict[str, str]) -> None:
        super().__init__([{}], max_retries=1)
        self._mapping = mapping
        self.config = FakeConfig(max_retries=1)

    async def complete_json(self, prompt, schema_name, *, json_schema=None) -> dict:
        self.calls += 1
        message = prompt.rsplit("\n", 1)[-1].strip()
        kind = self._mapping.get(message, "unknown")
        return {"kind": kind, "confidence": 0.9, "reason": "fake-llm"}


def _payload(text: str) -> SemanticMessageInput:
    return SemanticMessageInput(
        team_id=uuid4(),
        message_text=text,
        sender_user_id=uuid4(),
        team_timezone="Europe/Moscow",
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
        sender_display_name="Иван",
        team_members=["Иван", "Петя", "Оля"],
    )


NOISE_CASES = ["ок", "спасибо", "+", "принял", "да", "👍", "понял"]

LLM_CASES = {
    "Петя, подготовь оплату до четверга": "task_candidate",
    "Оля, сделай макет лендинга к понедельнику": "task_candidate",
    "давайте завтра созвонимся в 18:00": "meeting_candidate",
    "проверил интеграцию, всё готово": "daily_report",
    "я завтра на больничном": "absence_notice",
    "начал работать над задачей по платежам": "status_update",
}


@pytest.mark.parametrize("text", NOISE_CASES)
@pytest.mark.asyncio
async def test_russian_noise_is_prefiltered_without_llm(text: str) -> None:
    provider = MappedProvider({})
    parser = SemanticMessageParser(FakeFactory(provider, fallback=None))

    result = await parser.parse(_payload(text))

    assert result["kind"] == "noise"
    assert result["reason"] == "prefilter"
    assert provider.calls == 0  # LLM не вызывали


@pytest.mark.parametrize("text,expected", list(LLM_CASES.items()))
@pytest.mark.asyncio
async def test_russian_messages_classified_via_llm(text: str, expected: str) -> None:
    provider = MappedProvider(LLM_CASES)
    parser = SemanticMessageParser(FakeFactory(provider, fallback=None))

    result = await parser.parse(_payload(text))

    assert provider.calls >= 1  # содержательное сообщение дошло до LLM
    assert result["kind"] == expected
    # контракт semantic_message_v2: ключи всегда присутствуют
    for key in ("task", "meeting", "daily_report", "absence", "reason", "confidence"):
        assert key in result


@pytest.mark.asyncio
async def test_prompt_includes_team_context() -> None:
    captured: dict = {}

    class Capturing(MappedProvider):
        async def complete_json(self, prompt, schema_name, *, json_schema=None):
            captured["prompt"] = prompt
            return await super().complete_json(prompt, schema_name, json_schema=json_schema)

    provider = Capturing({"Петя, подготовь оплату до четверга": "task_candidate"})
    parser = SemanticMessageParser(FakeFactory(provider, fallback=None))
    await parser.parse(_payload("Петя, подготовь оплату до четверга"))

    assert "Europe/Moscow" in captured["prompt"]
    assert "team_members" in captured["prompt"]
    assert "Иван" in captured["prompt"]
