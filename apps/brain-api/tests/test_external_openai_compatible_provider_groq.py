"""ExternalOpenAICompatibleProvider против фейкового Groq-эндпоинта (httpx.MockTransport).

Тесты НЕ ходят в реальный Groq: весь HTTP подменён MockTransport.
"""

from __future__ import annotations

import json

import httpx
import pytest

from brain_api.infrastructure.llm.errors import (
    LLMInvalidJSONError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from brain_api.infrastructure.llm.providers import (
    ExternalOpenAICompatibleProvider,
    LLMProviderConfig,
    friendly_provider_name,
)

GROQ_BASE = "https://api.groq.com/openai/v1"
SEMANTIC_JSON = json.dumps(
    {"kind": "task_candidate", "confidence": 0.92, "reason": "явное поручение"}
)


def _config(transport: httpx.MockTransport, *, max_retries: int = 0) -> LLMProviderConfig:
    return LLMProviderConfig(
        provider="external_api",
        base_url=GROQ_BASE,
        model="llama-3.3-70b-versatile",
        api_key="gsk_test_key",
        timeout_seconds=5,
        max_retries=max_retries,
        strict_json=True,
        transport=transport,
    )


def _ok_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_friendly_provider_name() -> None:
    assert friendly_provider_name(GROQ_BASE) == "groq"
    assert friendly_provider_name("https://openrouter.ai/api/v1") == "openrouter"
    assert friendly_provider_name("http://ollama:11434/v1") == "ollama"


@pytest.mark.asyncio
async def test_groq_request_shape_and_auth() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return _ok_response(SEMANTIC_JSON)

    provider = ExternalOpenAICompatibleProvider(_config(httpx.MockTransport(handler)))
    result = await provider.complete_json(
        "классифицируй", "semantic_message_v2", json_schema={"name": "x", "schema": {}}
    )

    assert result["kind"] == "task_candidate"
    assert seen["url"] == f"{GROQ_BASE}/chat/completions"
    assert seen["auth"] == "Bearer gsk_test_key"
    assert seen["body"]["model"] == "llama-3.3-70b-versatile"
    assert seen["body"]["response_format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_json_object_when_no_schema() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return _ok_response(SEMANTIC_JSON)

    provider = ExternalOpenAICompatibleProvider(_config(httpx.MockTransport(handler)))
    result = await provider.complete_json("классифицируй", "semantic_message_v2")
    assert result["confidence"] == 0.92


@pytest.mark.asyncio
async def test_schema_downgrade_to_json_object_on_400() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": "json_schema not supported"})
        return _ok_response(SEMANTIC_JSON)

    provider = ExternalOpenAICompatibleProvider(_config(httpx.MockTransport(handler)))
    result = await provider.complete_json(
        "классифицируй", "semantic_message_v2", json_schema={"name": "x", "schema": {}}
    )
    assert result["kind"] == "task_candidate"
    assert calls == ["json_schema", "json_object"]


@pytest.mark.asyncio
async def test_rate_limit_maps_to_error() -> None:
    provider = ExternalOpenAICompatibleProvider(
        _config(httpx.MockTransport(lambda r: httpx.Response(429, json={})))
    )
    with pytest.raises(LLMRateLimitError):
        await provider.complete_json("x", "semantic_message_v2")


@pytest.mark.asyncio
async def test_server_error_maps_to_error() -> None:
    provider = ExternalOpenAICompatibleProvider(
        _config(httpx.MockTransport(lambda r: httpx.Response(503, json={})))
    )
    with pytest.raises(LLMServerError):
        await provider.complete_json("x", "semantic_message_v2")


@pytest.mark.asyncio
async def test_timeout_maps_to_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = ExternalOpenAICompatibleProvider(_config(httpx.MockTransport(handler)))
    with pytest.raises(LLMTimeoutError):
        await provider.complete_json("x", "semantic_message_v2")


@pytest.mark.asyncio
async def test_4xx_maps_to_unavailable() -> None:
    provider = ExternalOpenAICompatibleProvider(
        _config(httpx.MockTransport(lambda r: httpx.Response(401, json={})))
    )
    with pytest.raises(LLMUnavailableError):
        await provider.complete_json("x", "semantic_message_v2")


@pytest.mark.asyncio
async def test_invalid_json_content_raises() -> None:
    provider = ExternalOpenAICompatibleProvider(
        _config(httpx.MockTransport(lambda r: _ok_response("это не json")))
    )
    with pytest.raises(LLMInvalidJSONError):
        await provider.complete_json("x", "semantic_message_v2")
