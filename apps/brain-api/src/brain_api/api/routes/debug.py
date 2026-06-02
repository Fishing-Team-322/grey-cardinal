from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.container import Container
from brain_api.domain.enums import BoardProvider
from brain_api.infrastructure.board.base import YouGileConfig, resolve_provider

router = APIRouter(
    prefix="/internal/debug",
    tags=["internal-debug"],
    dependencies=[Depends(verify_internal_token)],
)


def _require_dev(container: Container) -> None:
    if container.settings.app_env != "dev":
        raise HTTPException(status_code=404, detail="Debug endpoints are available only in dev")


def _yougile_config(container: Container) -> YouGileConfig:
    settings = container.settings
    return YouGileConfig(
        api_base_url=settings.yougile_api_base_url,
        api_key=settings.yougile_api_key,
        company_id=settings.yougile_company_id or None,
        project_id=settings.yougile_project_id or None,
        board_id=settings.yougile_board_id or None,
        column_backlog_id=settings.yougile_column_backlog_id or None,
        column_todo_id=settings.yougile_column_todo_id or None,
        column_in_progress_id=settings.yougile_column_in_progress_id or None,
        column_review_id=settings.yougile_column_review_id or None,
        column_blocked_id=settings.yougile_column_blocked_id or None,
        column_done_id=settings.yougile_column_done_id or None,
    )


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
    provider = resolve_provider(container.settings.board_provider)
    yougile = _yougile_config(container)
    return {
        "ok": provider != BoardProvider.yougile or yougile.is_configured,
        "database": "ok",
        "board_provider": provider.value,
        "yougile_configured": yougile.is_configured,
        "yougile_missing": yougile.missing_required,
        "telegram_gateway_url": container.settings.telegram_bot_base_url,
    }
