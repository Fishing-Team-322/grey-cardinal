"""Read-side YouGile board endpoints and manual discovery trigger."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.deps import get_container
from brain_api.api.rbac import build_tenant_context, require_team_member, require_team_role
from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.application.use_cases.yougile_discovery import discover_yougile_workspace
from brain_api.config import get_settings
from brain_api.container import Container
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher

router = APIRouter(prefix="/api/teams/{team_id}/board", tags=["yougile-board"])
sync_router = APIRouter(
    prefix="/api/teams/{team_id}/integrations/yougile",
    tags=["yougile"],
)


class SelectBoardRequest(BaseModel):
    board_id: str
    column_mappings: dict[str, str | None] = Field(default_factory=dict)


@sync_router.get("/boards")
async def list_mirror_boards(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _team_for_member(team_id, current_user.id, session)
    boards = list(
        await session.scalars(
            select(m.YouGileBoardModel)
            .where(m.YouGileBoardModel.team_id == team_id)
            .order_by(m.YouGileBoardModel.name)
        )
    )
    result = []
    for board in boards:
        columns = list(
            await session.scalars(
                select(m.YouGileColumnModel)
                .where(m.YouGileColumnModel.board_id == board.id)
                .order_by(m.YouGileColumnModel.position)
            )
        )
        result.append(
            {
                "id": board.external_id,
                "name": board.name,
                "is_selected": board.is_selected,
                "columns": [
                    {
                        "id": column.external_id,
                        "name": column.name,
                        "mapped_status": column.mapped_status,
                        "position": column.position,
                    }
                    for column in columns
                ],
            }
        )
    return result


@sync_router.get("/boards/{board_id}/columns")
async def list_mirror_columns(
    team_id: UUID,
    board_id: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    boards = await list_mirror_boards(team_id, current_user, session)
    board = next((item for item in boards if item["id"] == board_id), None)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "YouGile board not found")
    return board["columns"]


@sync_router.post("/select-board")
async def select_mirror_board(
    team_id: UUID,
    body: SelectBoardRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, team_id, "manager")
    boards = list(
        await session.scalars(
            select(m.YouGileBoardModel).where(m.YouGileBoardModel.team_id == team_id)
        )
    )
    selected = next((row for row in boards if row.external_id == body.board_id), None)
    if selected is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "YouGile board not found")
    for board in boards:
        board.is_selected = board.id == selected.id
    columns = list(
        await session.scalars(
            select(m.YouGileColumnModel).where(m.YouGileColumnModel.board_id == selected.id)
        )
    )
    allowed = {"backlog", "todo", "in_progress", "blocked", "review", "done"}
    used: set[str] = set()
    for column in columns:
        mapped = body.column_mappings.get(column.external_id)
        if mapped is not None and mapped not in allowed:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid task status")
        if mapped and mapped in used:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Status {mapped} is mapped more than once",
            )
        column.mapped_status = mapped
        if mapped:
            used.add(mapped)
    team = await session.get(m.TeamModel, team_id)
    assert team is not None
    config = dict(team.board_config or {})
    config["default_board_id"] = selected.external_id
    config["default_column_ids"] = {
        column.mapped_status: column.external_id
        for column in columns
        if column.mapped_status
    }
    team.board_config = config
    await session.commit()
    return {
        "selected_board": {"id": selected.external_id, "name": selected.name},
        "mapped_statuses": sorted(used),
    }


@sync_router.post("/import")
async def import_mirror_board(
    team_id: UUID,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, team_id, "manager")
    return (await container.board_mirror.import_selected_board(team_id)).payload()


@sync_router.get("/sync-events")
async def list_sync_events(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _team_for_member(team_id, current_user.id, session)
    rows = list(
        await session.scalars(
            select(m.SyncEventModel)
            .where(m.SyncEventModel.team_id == team_id)
            .order_by(m.SyncEventModel.created_at.desc())
            .limit(100)
        )
    )
    return [
        {
            "id": str(row.id),
            "task_id": str(row.task_id) if row.task_id else None,
            "direction": row.direction,
            "action": row.action,
            "status": row.status,
            "error": row.error,
            "created_at": row.created_at,
        }
        for row in rows
    ]


async def _team_for_member(
    team_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> m.TeamModel:
    ctx = await build_tenant_context(user_id, session)
    require_team_member(ctx, team_id)
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    return team


async def _mappings(
    session: AsyncSession,
    team_id: UUID,
    entity_type: str,
) -> list[m.YouGileMappingModel]:
    rows = await session.execute(
        select(m.YouGileMappingModel).where(
            m.YouGileMappingModel.team_id == team_id,
            m.YouGileMappingModel.entity_type == entity_type,
        )
    )
    return list(rows.scalars().all())


@router.get("/projects")
async def list_projects(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    team = await _team_for_member(team_id, current_user.id, session)
    primary_id = str((team.board_config or {}).get("yougile_project_id") or "")
    projects = await _mappings(session, team_id, "project")
    boards = await _mappings(session, team_id, "board")
    board_count: dict[str, int] = {}
    for board in boards:
        project_id = str((board.payload or {}).get("projectId") or "")
        board_count[project_id] = board_count.get(project_id, 0) + 1
    return [
        {
            "id": row.yougile_id,
            "name": _name(row.payload),
            "is_primary": row.yougile_id == primary_id,
            "boards_count": board_count.get(row.yougile_id, 0),
        }
        for row in projects
    ]


@router.get("/projects/{project_id}/boards")
async def list_project_boards(
    team_id: UUID,
    project_id: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _team_for_member(team_id, current_user.id, session)
    boards = [
        row
        for row in await _mappings(session, team_id, "board")
        if str((row.payload or {}).get("projectId")) == project_id
    ]
    columns = await _mappings(session, team_id, "column")
    tasks = await _mappings(session, team_id, "task")
    task_count: dict[str, int] = {}
    for task in tasks:
        column_id = str((task.payload or {}).get("columnId") or "")
        task_count[column_id] = task_count.get(column_id, 0) + 1
    return [
        {
            "id": board.yougile_id,
            "name": _name(board.payload),
            "columns": [
                {
                    "id": column.yougile_id,
                    "name": _name(column.payload),
                    "tasks_count": task_count.get(column.yougile_id, 0),
                }
                for column in columns
                if str((column.payload or {}).get("boardId")) == board.yougile_id
            ],
        }
        for board in boards
    ]


@router.get("/columns/{column_id}/tasks")
async def list_column_tasks(
    team_id: UUID,
    column_id: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _team_for_member(team_id, current_user.id, session)
    tasks = [
        row
        for row in await _mappings(session, team_id, "task")
        if str((row.payload or {}).get("columnId")) == column_id
    ]
    users = {row.yougile_id: row for row in await _mappings(session, team_id, "user")}
    return [_task_payload(row, users) for row in tasks]


@sync_router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    team_id: UUID,
    current_user: CurrentUser,
    background: BackgroundTasks,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, team_id, "manager")
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    if not team.board_credentials_encrypted:
        raise HTTPException(status.HTTP_409_CONFLICT, "YouGile is not connected")

    job_id = str(uuid4())
    settings = get_settings()
    background.add_task(
        _run_sync_job,
        container,
        team_id,
        job_id,
        settings.yougile_api_base_url,
        SecretCipher(settings.board_creds_encryption_key or "dev-key"),
    )
    return {"job_id": job_id}


async def _run_sync_job(
    container: Container,
    team_id: UUID,
    job_id: str,
    api_base_url: str,
    cipher: SecretCipher,
) -> None:
    await _publish_progress(container, team_id, job_id, "started", 0)
    result = await discover_yougile_workspace(
        container.session_factory,
        team_id=team_id,
        api_base_url=api_base_url,
        cipher=cipher,
    )
    mirror_result = None
    if result.get("ok"):
        try:
            mirror_result = await container.board_mirror.sync_inbound(team_id)
        except Exception as exc:  # noqa: BLE001
            mirror_result = {"errors": [str(exc)]}
    if mirror_result is not None:
        result["mirror"] = mirror_result
    await _publish_progress(
        container,
        team_id,
        job_id,
        "completed" if result.get("ok") else "failed",
        100,
        result,
    )


async def _publish_progress(
    container: Container,
    team_id: UUID,
    job_id: str,
    state: str,
    progress: int,
    result: dict[str, Any] | None = None,
) -> None:
    # The current shared contract has a fixed enum. Broadcast the new event
    # directly until the frontend contract is expanded in its own release.
    await container.websocket_manager.broadcast(
        {
            "event": "yougile_sync_progress",
            "payload": {
                "team_id": str(team_id),
                "job_id": job_id,
                "state": state,
                "progress": progress,
                "result": result,
            },
        }
    )


def _name(payload: dict[str, Any] | None) -> str:
    payload = payload or {}
    return str(payload.get("title") or payload.get("name") or "")


def _task_payload(
    row: m.YouGileMappingModel,
    users: dict[str, m.YouGileMappingModel],
) -> dict[str, Any]:
    payload = row.payload or {}
    assigned = []
    for yougile_user_id in payload.get("assigned") or []:
        mapping = users.get(str(yougile_user_id))
        user_payload = mapping.payload if mapping else {}
        assigned.append(
            {
                "yougile_user_id": str(yougile_user_id),
                "local_user_id": str(mapping.local_id) if mapping and mapping.local_id else None,
                "name": (user_payload or {}).get("realName")
                or (user_payload or {}).get("email")
                or "",
            }
        )
    stickers = [
        {"id": sticker_id, "value": value}
        for sticker_id, value in (payload.get("stickers") or {}).items()
    ]
    return {
        "id": row.yougile_id,
        "local_id": str(row.local_id) if row.local_id else None,
        "title": payload.get("title") or "",
        "assigned": assigned,
        "deadline": _deadline_iso(payload.get("deadline")),
        "stickers": stickers,
    }


def _deadline_iso(value: Any) -> str | None:
    if not isinstance(value, dict) or not value.get("deadline"):
        return None
    return datetime.fromtimestamp(float(value["deadline"]) / 1000, tz=UTC).isoformat()
