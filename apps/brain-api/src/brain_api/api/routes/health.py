"""Health/readiness endpoints."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from brain_api.api.deps import get_container
from brain_api.container import Container

router = APIRouter(tags=["health"])

ALEMBIC_HEAD = "0001_initial_v2"


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "brain-api"}


@router.get("/api/health")
async def api_health() -> dict[str, str]:
    return await health()


@router.get("/ready")
async def ready(container: Container = Depends(get_container)) -> dict:
    report = await dependency_report(container)
    required = report["checks"]
    failed = [name for name, check in required.items() if not check["ok"]]
    if failed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "failed": failed, "checks": required},
        )
    return {"status": "ready", "checks": required}


@router.get("/api/ready")
async def api_ready(container: Container = Depends(get_container)) -> dict:
    return await ready(container)


@router.get("/internal/debug/health/dependencies")
async def dependency_report(container: Container = Depends(get_container)) -> dict:
    settings = container.settings
    checks: dict[str, dict[str, object]] = {}
    checks["db"] = await _check_db(container)
    checks["migrations"] = await _check_migrations(container)
    checks["production_config"] = _check_production_config(container)
    checks["llm"] = await _check_llm(container)
    checks["telegram_config"] = {
        "ok": bool(settings.telegram_bot_token) or not settings.is_production,
        "mode": settings.telegram_mode,
    }
    checks["storage"] = _check_storage(container)
    return {
        "status": "ok" if all(c["ok"] for c in checks.values()) else "unhealthy",
        "checks": checks,
    }


async def _check_db(container: Container) -> dict[str, object]:
    try:
        async with container.session_factory() as session:
            await session.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def _check_migrations(container: Container) -> dict[str, object]:
    if not container.settings.is_production:
        return {"ok": True, "required": ALEMBIC_HEAD, "skipped": "non-production"}
    try:
        async with container.session_factory() as session:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            versions = {row[0] for row in result.all()}
        return {
            "ok": ALEMBIC_HEAD in versions,
            "required": ALEMBIC_HEAD,
            "versions": sorted(versions),
        }
    except Exception as exc:
        return {"ok": False, "required": ALEMBIC_HEAD, "error": str(exc)}


def _check_production_config(container: Container) -> dict[str, object]:
    errors = container.settings.production_config_errors()
    return {"ok": not errors, "errors": errors}


async def _check_llm(container: Container) -> dict[str, object]:
    settings = container.settings
    if not settings.llm_enabled:
        return {"ok": not settings.is_production, "provider": settings.llm_provider}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.effective_llm_base_url.rstrip('/')}/models")
        return {
            "ok": response.status_code < 500,
            "provider": settings.llm_provider,
            "status_code": response.status_code,
        }
    except Exception as exc:
        return {
            "ok": not settings.is_production,
            "provider": settings.llm_provider,
            "error": str(exc),
        }


def _check_storage(container: Container) -> dict[str, object]:
    failures: list[str] = []
    for path in container.settings.storage_paths:
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            probe = Path(path) / ".ready_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as exc:
            failures.append(f"{path}: {exc}")
    return {"ok": not failures, "errors": failures}
