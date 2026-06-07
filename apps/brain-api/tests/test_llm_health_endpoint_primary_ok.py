"""Health-report: primary отвечает -> status ok, fallback помечен configured.

Тестируем чистую функцию llm_health_report с fake-провайдерами (без подъёма
FastAPI-приложения и без реальных HTTP-вызовов).
"""

from __future__ import annotations

import pytest
from llm_fakes import FakeConfig, FakeProvider

from brain_api.application.llm.health import llm_health_report
from brain_api.infrastructure.llm.providers import ResolvedLLM


@pytest.mark.asyncio
async def test_primary_ok_reports_status_ok_with_latency() -> None:
    primary = FakeProvider([{"ok": True, "kind": "healthcheck"}])
    primary.config = FakeConfig(model="llama-3.3-70b-versatile", base_url="https://api.groq.com/openai/v1")
    fallback = FakeProvider([{"ok": True}])
    fallback.config = FakeConfig(model="deepseek/deepseek-chat-v3:free", base_url="https://openrouter.ai/api/v1")

    report = await llm_health_report(ResolvedLLM(primary=primary, fallback=fallback))

    assert report["status"] == "ok"
    assert report["primary"]["model"] == "llama-3.3-70b-versatile"
    assert report["primary"]["base_url"] == "https://api.groq.com/openai/v1"
    assert isinstance(report["primary"]["latency_ms"], int)
    assert "error" not in report["primary"]
    # fallback при здоровом primary только помечается configured, его не дёргаем
    assert report["fallback"]["enabled"] is True
    assert report["fallback"]["status"] == "configured"
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_primary_ok_without_fallback() -> None:
    primary = FakeProvider([{"ok": True, "kind": "healthcheck"}])
    report = await llm_health_report(ResolvedLLM(primary=primary, fallback=None))

    assert report["status"] == "ok"
    assert report["fallback"] == {"enabled": False}


@pytest.mark.asyncio
async def test_health_report_never_contains_api_key() -> None:
    primary = FakeProvider([{"ok": True, "kind": "healthcheck"}])
    primary.config = FakeConfig(model="m", base_url="https://api.groq.com/openai/v1")
    report = await llm_health_report(ResolvedLLM(primary=primary, fallback=None))

    flat = str(report).lower()
    assert "api_key" not in flat
    assert "authorization" not in flat
    assert "bearer" not in flat
