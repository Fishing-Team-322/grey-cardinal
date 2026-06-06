from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.container import Container

router = APIRouter(
    prefix="/internal/debug",
    tags=["internal-debug"],
    dependencies=[Depends(verify_internal_token)],
)


def _require_dev(container: Container) -> None:
    if container.settings.app_env != "dev":
        raise HTTPException(status_code=404, detail="Debug endpoints are available only in dev")


@router.get("/state")
async def state(container: Container = Depends(get_container)) -> dict[str, int]:
    _require_dev(container)
    async with container.make_uow() as uow:
        return await uow.debug.counts()


@router.get("/health/dependencies")
async def dependencies(container: Container = Depends(get_container)) -> dict[str, object]:
    _require_dev(container)
    async with container.make_uow() as uow:
        await uow.debug.counts()
    return {
        "ok": True,
        "database": "ok",
        "board_provider": "team-scoped",
        "yougile_configuration": "encrypted per team",
        "telegram_gateway_url": container.settings.telegram_bot_base_url,
    }
