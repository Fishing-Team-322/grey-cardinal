"""Health-report: primary падает -> зондируем fallback, отдаём его реальный статус."""

from __future__ import annotations

import pytest
from llm_fakes import FakeConfig, FakeProvider

from brain_api.application.llm.health import llm_health_report
from brain_api.infrastructure.llm.errors import LLMServerError, LLMTimeoutError
from brain_api.infrastructure.llm.providers import ResolvedLLM


@pytest.mark.asyncio
async def test_primary_fail_fallback_ok() -> None:
    primary = FakeProvider([LLMTimeoutError("timeout")])
    primary.config = FakeConfig(model="llama-3.3-70b-versatile", base_url="https://api.groq.com/openai/v1")
    fallback = FakeProvider([{"ok": True, "kind": "healthcheck"}])
    fallback.config = FakeConfig(model="deepseek/deepseek-chat-v3:free", base_url="https://openrouter.ai/api/v1")

    report = await llm_health_report(ResolvedLLM(primary=primary, fallback=fallback))

    assert report["status"] == "error"
    assert report["primary"]["error"] == "timeout"
    assert "latency_ms" not in report["primary"]
    # fallback реально зондируется и спасает
    assert fallback.calls == 1
    assert report["fallback"]["enabled"] is True
    assert report["fallback"]["status"] == "ok"
    assert isinstance(report["fallback"]["latency_ms"], int)


@pytest.mark.asyncio
async def test_primary_fail_fallback_also_fails() -> None:
    primary = FakeProvider([LLMServerError("500")])
    fallback = FakeProvider([LLMTimeoutError("timeout")])

    report = await llm_health_report(ResolvedLLM(primary=primary, fallback=fallback))

    assert report["status"] == "error"
    assert report["primary"]["error"] == "server_error"
    assert report["fallback"]["status"] == "error"
    assert report["fallback"]["error"] == "timeout"


@pytest.mark.asyncio
async def test_primary_fail_no_fallback() -> None:
    primary = FakeProvider([LLMServerError("500")])
    report = await llm_health_report(ResolvedLLM(primary=primary, fallback=None))

    assert report["status"] == "error"
    assert report["fallback"] == {"enabled": False}
