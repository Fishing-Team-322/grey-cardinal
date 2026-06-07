"""Health/readiness endpoints."""

from __future__ import annotations

from pathlib import Path

import httpx
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from brain_api.api.deps import get_container
from brain_api.container import Container

router = APIRouter(tags=["health"])


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
        return {"ok": True, "required": sorted(_alembic_heads()), "skipped": "non-production"}
    required: set[str] = set()
    try:
        required = _alembic_heads()
        async with container.session_factory() as session:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            versions = {row[0] for row in result.all()}
        return {
            "ok": versions == required,
            "required": sorted(required),
            "versions": sorted(versions),
        }
    except Exception as exc:
        return {"ok": False, "required": sorted(required), "error": str(exc)}


def _alembic_heads() -> set[str]:
    app_dir = Path(__file__).resolve().parents[4]
    config = Config(str(app_dir / "alembic.ini"))
    config.set_main_option("script_location", str(app_dir / "alembic"))
    return set(ScriptDirectory.from_config(config).get_heads())


def _check_production_config(container: Container) -> dict[str, object]:
    errors = container.settings.production_config_errors()
    return {"ok": not errors, "errors": errors}


async def _check_llm(container: Container) -> dict[str, object]:
    settings = container.settings
    if not settings.llm_enabled:
        return {"ok": not settings.is_production, "provider": settings.llm_provider}
    # Probe through the same proxy the extractor uses, so /ready reflects the
    # real egress (Groq is geo-blocked without the VPN). local → never proxied.
    client_kwargs: dict = {"timeout": 5.0}
    if settings.llm_provider != "local" and settings.llm_proxy:
        client_kwargs["proxy"] = settings.llm_proxy
    headers = {}
    if settings.llm_provider == "external_api" and settings.effective_llm_api_key:
        headers["Authorization"] = f"Bearer {settings.effective_llm_api_key}"
    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.get(
                f"{settings.effective_llm_base_url.rstrip('/')}/models",
                headers=headers,
            )
        return {
            "ok": 200 <= response.status_code < 300,
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
