from datetime import UTC, datetime
from uuid import uuid4

import pytest

from brain_api.application.semantic_parser import SemanticMessageInput, SemanticMessageParser


class _Provider:
    config = type("Config", (), {"max_retries": 0})()

    async def complete_json(
        self, prompt: str, schema_name: str, *, json_schema: dict | None = None
    ) -> dict:
        assert schema_name == "semantic_message_v2"
        assert "Europe/Moscow" in prompt
        return {
            "kind": "task_candidate",
            "confidence": 0.9,
            "business_relevance": 0.95,
            "is_actionable": True,
            "is_abusive": False,
            "is_vague": False,
            "should_create_proposal": True,
            "task": {"title": "Prepare invoice", "priority": "high"},
        }


class _Factory:
    async def for_team(self, team_id):
        return _Provider()

    async def resolve_for_team(self, team_id):
        from brain_api.infrastructure.llm.providers import ResolvedLLM

        return ResolvedLLM(primary=_Provider(), fallback=None)


@pytest.mark.asyncio
async def test_semantic_message_parser_contract():
    parser = SemanticMessageParser(_Factory())
    result = await parser.parse(
        SemanticMessageInput(
            team_id=uuid4(),
            message_text="Петя, подготовь оплату завтра до 18:00",
            sender_user_id=uuid4(),
            team_timezone="Europe/Moscow",
            now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
        )
    )

    assert result["kind"] == "task_candidate"
    assert result["confidence"] == 0.9
    assert result["meeting"] is None
