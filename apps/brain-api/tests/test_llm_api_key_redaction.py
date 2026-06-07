"""LLM-вызовы не должны раскрывать API-ключи и Authorization-заголовки.

Покрываем хелперы redaction и проверяем, что метрики провайдера не содержат
секрета даже при «болтливом» логировании.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from brain_api.infrastructure.llm.providers import (
    LLMProviderConfig,
    OpenAICompatibleJSONProvider,
)
from brain_api.infrastructure.llm.redaction import (
    redact_authorization_headers,
    redact_secret,
)

SECRET = "gsk_1234567890abcdefSECRET"


def test_redact_secret_masks_middle() -> None:
    masked = redact_secret(SECRET)
    assert SECRET not in masked
    assert masked.startswith("gsk_")
    assert masked.endswith(SECRET[-4:])
    assert "***" in masked


def test_redact_secret_short_and_empty() -> None:
    assert redact_secret("short") == "***redacted***"
    assert redact_secret("") == ""
    assert redact_secret(None) == ""


def test_redact_authorization_headers() -> None:
    headers = {
        "Authorization": f"Bearer {SECRET}",
        "X-API-Key": SECRET,
        "Content-Type": "application/json",
    }
    redacted = redact_authorization_headers(headers)
    assert redacted["Authorization"] == "***redacted***"
    assert redacted["X-API-Key"] == "***redacted***"
    assert redacted["Content-Type"] == "application/json"
    # исходный словарь не мутируется
    assert headers["Authorization"] == f"Bearer {SECRET}"


def test_redact_empty_headers() -> None:
    assert redact_authorization_headers(None) == {}
    assert redact_authorization_headers({}) == {}


@pytest.mark.asyncio
async def test_provider_metrics_never_log_api_key(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # ключ действительно уходит в Authorization, но логи его раскрывать не должны
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"ok": True})}}]},
        )

    config = LLMProviderConfig(
        provider="external_api",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile",
        api_key=SECRET,
        timeout_seconds=5,
        max_retries=0,
        strict_json=True,
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAICompatibleJSONProvider(config)

    with caplog.at_level(logging.DEBUG):
        await provider.complete_json("Верни JSON {\"ok\": true}", "healthcheck")

    for record in caplog.records:
        assert SECRET not in record.getMessage()
