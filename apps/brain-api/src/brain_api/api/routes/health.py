"""Health/readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
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
async def ready(container: Container = Depends(get_container)) -> dict[str, str]:
    """Готовность: проверяем доступность БД."""
    async with container.session_factory() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/api/ready")
async def api_ready(container: Container = Depends(get_container)) -> dict[str, str]:
    return await ready(container)
