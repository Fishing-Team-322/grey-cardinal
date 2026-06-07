"""LLM health-probe, который реально вызывает выбранного провайдера.

Логика вынесена из FastAPI-роутера, чтобы её можно было юнит-тестировать с
fake-провайдерами без подъёма всего приложения (см. ТЗ: health реально вызывает
provider, не раскрывает secrets).

Стратегия (совпадает с примерами из ТЗ):
  * Всегда зондируем primary.
  * Если primary OK — fallback просто помечаем как ``configured`` (не дёргаем его
    зря, чтобы не жечь лимиты).
  * Если primary упал — зондируем fallback и возвращаем его реальный статус.

Ни ``api_key``, ни ``Authorization`` в ответ не попадают: наружу отдаём только
provider/base_url/model/latency/error-category.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from brain_api.infrastructure.llm.errors import LLMError
from brain_api.infrastructure.llm.providers import LLMProvider, ResolvedLLM

# Короткий JSON-тест: в промпте есть слово "JSON" (нужно для json_object mode).
_HEALTH_PROMPT = 'Верни строго JSON {"ok": true, "kind": "healthcheck"} без markdown.'
_HEALTH_SCHEMA = "healthcheck"


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    provider: str
    model: str
    base_url: str
    latency_ms: int | None = None
    error: str | None = None


def _provider_meta(provider: LLMProvider) -> tuple[str, str, str]:
    config = getattr(provider, "config", None)
    label = getattr(config, "label", None) or getattr(config, "provider", "external_api")
    model = getattr(config, "model", "") or ""
    base_url = getattr(config, "base_url", "") or ""
    return str(label), str(model), str(base_url)


async def probe_provider(provider: LLMProvider) -> ProbeResult:
    """Реально дёрнуть провайдера коротким JSON-промптом и измерить latency."""
    label, model, base_url = _provider_meta(provider)
    started = time.perf_counter()
    try:
        data = await provider.complete_json(_HEALTH_PROMPT, _HEALTH_SCHEMA)
    except LLMError as exc:
        return ProbeResult(
            ok=False, provider=label, model=model, base_url=base_url, error=exc.category
        )
    except Exception as exc:  # noqa: BLE001 — любой сбой это «provider не здоров»
        return ProbeResult(
            ok=False, provider=label, model=model, base_url=base_url, error=type(exc).__name__
        )
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not isinstance(data, dict):
        return ProbeResult(
            ok=False, provider=label, model=model, base_url=base_url,
            latency_ms=latency_ms, error="invalid_json",
        )
    return ProbeResult(
        ok=True, provider=label, model=model, base_url=base_url, latency_ms=latency_ms
    )


def _primary_public(probe: ProbeResult) -> dict:
    if probe.ok:
        return {
            "provider": probe.provider,
            "base_url": probe.base_url,
            "model": probe.model,
            "latency_ms": probe.latency_ms,
        }
    return {"provider": probe.provider, "model": probe.model, "error": probe.error}


async def llm_health_report(resolved: ResolvedLLM) -> dict:
    """Собрать ответ health-check по контракту ТЗ (primary + fallback)."""
    primary_probe = await probe_provider(resolved.primary)
    report: dict = {"primary": _primary_public(primary_probe)}

    if primary_probe.ok:
        report["status"] = "ok"
        if resolved.fallback is not None:
            label, model, base_url = _provider_meta(resolved.fallback)
            report["fallback"] = {
                "enabled": True,
                "provider": label,
                "base_url": base_url,
                "model": model,
                "status": "configured",
            }
        else:
            report["fallback"] = {"enabled": False}
        return report

    # Primary упал — проверяем, спасает ли fallback.
    report["status"] = "error"
    if resolved.fallback is not None:
        fallback_probe = await probe_provider(resolved.fallback)
        fallback: dict = {
            "enabled": True,
            "provider": fallback_probe.provider,
            "base_url": fallback_probe.base_url,
            "model": fallback_probe.model,
            "status": "ok" if fallback_probe.ok else "error",
        }
        if fallback_probe.ok:
            fallback["latency_ms"] = fallback_probe.latency_ms
        else:
            fallback["error"] = fallback_probe.error
        report["fallback"] = fallback
    else:
        report["fallback"] = {"enabled": False}
    return report
