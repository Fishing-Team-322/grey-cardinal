"""Agentic PM product APIs: Grey Board, AI Inbox, setup, maps, profiles."""
# ruff: noqa: E501

from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.rbac import (
    build_tenant_context,
    require_company_role,
    require_team_member,
    require_team_role,
)
from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.application.use_cases.agentic_pm import (
    YouGileFullSyncService,
    ai_inbox_payload,
    company_map_payload,
    employee_profile_payload,
    grey_board_payload,
    recommendations_for_team,
)
from brain_api.config import get_settings
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher
from brain_api.integrations.yougile import YouGileAuthError, YouGileClient, YouGileError

router = APIRouter(tags=["agentic-pm"])


class YouGileConnectRequest(BaseModel):
    api_key: str | None = None
    login: str | None = None
    password: str | None = None
    company_id: str | None = None


class SelectBoardRequest(BaseModel):
    board_id: str
    column_mapping: dict[str, str] | None = None


class InboxEditRequest(BaseModel):
    parsed_payload: dict[str, Any] | None = None
    source_text: str | None = None
    proposed_action: str | None = None


class LinkTaskRequest(BaseModel):
    task_id: UUID


class TopicBindRequest(BaseModel):
    telegram_chat_id: UUID
    message_thread_id: int
    board_id: UUID | None = None
    source_name: str | None = None


class TaskActionRequest(BaseModel):
    action: str
    assignee_id: UUID | None = None
    deadline: datetime | None = None
    comment: str | None = None


async def _require_team(
    session: AsyncSession,
    user_id: UUID,
    team_id: UUID,
    *,
    manager: bool = False,
) -> m.TeamModel:
    ctx = await build_tenant_context(user_id, session)
    if manager:
        require_team_role(ctx, team_id, "manager")
    else:
        require_team_member(ctx, team_id)
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    return team


def _cipher() -> SecretCipher:
    settings = get_settings()
    return SecretCipher(settings.board_creds_encryption_key or "dev-key")


def _sync_service(session: AsyncSession, team_id: UUID) -> YouGileFullSyncService:
    settings = get_settings()
    return YouGileFullSyncService(
        session,
        team_id=team_id,
        cipher=_cipher(),
        api_base_url=settings.yougile_api_base_url,
    )


@router.post("/api/teams/{team_id}/yougile/connect")
async def connect_yougile(
    team_id: UUID,
    body: YouGileConnectRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    team = await _require_team(session, current_user.id, team_id, manager=True)
    settings = get_settings()
    api_key = body.api_key
    company: dict[str, Any] | None = None
    if not api_key:
        if not body.login or not body.password or not body.company_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "api_key or login/password/company_id required")
        client = YouGileClient("", base_url=settings.yougile_api_base_url)
        try:
            keys = await client.auth_keys_get(body.login, body.password, body.company_id)
            api_key = keys[0]["key"] if keys else await client.auth_keys_create(body.login, body.password, body.company_id)
            companies = await client.auth_companies(body.login, body.password)
            company = next((item for item in companies if str(item.get("id")) == body.company_id), None)
        except YouGileAuthError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"error": "invalid_credentials"}) from exc
        except YouGileError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, {"error": "yougile_unavailable"}) from exc

    assert api_key is not None
    credentials = _cipher().encrypt_text(json.dumps({"api_key": api_key}))
    connection = await session.scalar(
        select(m.YouGileConnectionModel).where(
            m.YouGileConnectionModel.team_id == team_id,
            m.YouGileConnectionModel.provider == "yougile",
        )
    )
    if connection is None:
        connection = m.YouGileConnectionModel(
            id=uuid4(),
            team_id=team_id,
            provider="yougile",
            credentials_encrypted=credentials,
            status="active",
        )
    connection.credentials_encrypted = credentials
    connection.status = "active"
    connection.last_error = None
    connection.last_checked_at = datetime.now(UTC)
    team.board_provider = "yougile"
    team.board_credentials_encrypted = credentials
    config = dict(team.board_config or {})
    if body.company_id:
        config["yougile_company_id"] = body.company_id
        config["yougile_company_name"] = (company or {}).get("name")
    config["integration_status"] = "connected"
    team.board_config = config
    session.add_all([team, connection])
    await session.commit()

    service = _sync_service(session, team_id)
    stats = await service.refresh_catalog()
    return {"connected": True, "status": "active", "company": company, "stats": stats}


@router.get("/api/teams/{team_id}/yougile/status")
async def yougile_status(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    team = await _require_team(session, current_user.id, team_id)
    connection = await session.scalar(
        select(m.YouGileConnectionModel).where(m.YouGileConnectionModel.team_id == team_id)
    )
    selected = await session.scalar(
        select(m.YouGileBoardModel).where(
            m.YouGileBoardModel.team_id == team_id,
            m.YouGileBoardModel.is_selected.is_(True),
        )
    )
    counts = {}
    for name, model in {
        "workspaces": m.YouGileWorkspaceModel,
        "projects": m.YouGileProjectModel,
        "boards": m.YouGileBoardModel,
        "columns": m.YouGileColumnModel,
        "tasks": m.ExternalTaskLinkModel,
    }.items():
        statement = select(func.count()).select_from(model)
        if hasattr(model, "team_id"):
            statement = statement.where(model.team_id == team_id)
        elif connection is not None and hasattr(model, "connection_id"):
            statement = statement.where(model.connection_id == connection.id)
        counts[name] = int(await session.scalar(statement) or 0)
    return {
        "connected": connection is not None or bool(team.board_credentials_encrypted),
        "status": connection.status if connection else (team.board_config or {}).get("integration_status"),
        "last_checked_at": connection.last_checked_at if connection else None,
        "last_error": connection.last_error if connection else None,
        "selected_board": {
            "id": str(selected.id),
            "external_id": selected.external_id,
            "name": selected.name,
        } if selected else None,
        "stats": counts,
    }


@router.get("/api/teams/{team_id}/yougile/workspaces")
async def list_workspaces(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id)
    connection = await _sync_service(session, team_id).active_connection()
    rows = (
        (
            await session.execute(
                select(m.YouGileWorkspaceModel).where(m.YouGileWorkspaceModel.connection_id == connection.id)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_external_payload(row) for row in rows]}


@router.get("/api/teams/{team_id}/yougile/projects")
async def list_projects(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id)
    connection = await _sync_service(session, team_id).active_connection()
    rows = (
        (
            await session.execute(
                select(m.YouGileProjectModel).where(m.YouGileProjectModel.connection_id == connection.id).order_by(m.YouGileProjectModel.name)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_external_payload(row) for row in rows]}


@router.get("/api/teams/{team_id}/yougile/boards")
async def list_boards(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await _require_team(session, current_user.id, team_id)
    rows = (
        (
            await session.execute(
                select(m.YouGileBoardModel).where(m.YouGileBoardModel.team_id == team_id).order_by(m.YouGileBoardModel.name)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_board_payload(row) for row in rows]}


@router.get("/api/teams/{team_id}/yougile/boards/{board_id}/columns")
async def list_columns(
    team_id: UUID,
    board_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await _require_team(session, current_user.id, team_id)
    board = await session.get(m.YouGileBoardModel, board_id)
    if board is None or board.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Board not found")
    rows = (
        (
            await session.execute(
                select(m.YouGileColumnModel).where(m.YouGileColumnModel.board_id == board_id).order_by(m.YouGileColumnModel.position)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_column_payload(row) for row in rows]}


@router.post("/api/teams/{team_id}/yougile/select-board")
async def select_board(
    team_id: UUID,
    body: SelectBoardRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await _require_team(session, current_user.id, team_id, manager=True)
    try:
        return await _sync_service(session, team_id).select_board(body.board_id, body.column_mapping)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/api/teams/{team_id}/yougile/import")
async def import_board(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id, manager=True)
    try:
        return await _sync_service(session, team_id).import_selected_board()
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/api/teams/{team_id}/yougile/sync")
async def sync_board(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id, manager=True)
    try:
        return await _sync_service(session, team_id).sync_selected_board()
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/api/teams/{team_id}/yougile/sync-events")
async def sync_events(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id)
    rows = (
        (
            await session.execute(
                select(m.SyncEventModel).where(m.SyncEventModel.team_id == team_id).order_by(m.SyncEventModel.created_at.desc()).limit(100)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_sync_event_payload(row) for row in rows]}


@router.get("/api/teams/{team_id}/grey-board")
async def grey_board(
    team_id: UUID,
    current_user: CurrentUser,
    view: str = Query(default="agent"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    await _require_team(session, current_user.id, team_id)
    return await grey_board_payload(session, team_id, view)


@router.post("/api/tasks/{task_id}/agent-action")
async def task_action(
    task_id: UUID,
    body: TaskActionRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    task = await session.get(m.TaskModel, task_id)
    if task is None or task.team_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await _require_team(session, current_user.id, task.team_id)
    mapping = {
        "start": "in_progress",
        "done": "done",
        "blocked": "blocked",
        "review": "review",
        "wont_do": "cancelled",
    }
    if body.action in mapping:
        task.status = mapping[body.action]
        task.last_status_update_at = datetime.now(UTC)
        if task.status == "done":
            task.completed_at = datetime.now(UTC)
    if body.assignee_id:
        task.assignee_id = body.assignee_id
    if body.deadline:
        task.deadline = body.deadline
    session.add(task)
    await session.commit()
    if task.team_id:
        with suppress(Exception):
            await _sync_service(session, task.team_id).sync_selected_board()
    return {"ok": True, "task_id": str(task.id), "status": task.status}


@router.get("/api/teams/{team_id}/ai-inbox")
async def ai_inbox(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id)
    payload = await ai_inbox_payload(session, team_id)
    await session.commit()
    return payload


@router.post("/api/ai-inbox/{item_id}/approve")
async def approve_inbox(item_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    item = await _inbox_item(session, item_id, current_user.id, manager=True)
    item.status = "approved"
    item.decided_by = current_user.id
    item.decided_at = datetime.now(UTC)
    session.add(item)
    await session.commit()
    return {"status": "approved"}


@router.post("/api/ai-inbox/{item_id}/reject")
async def reject_inbox(item_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    item = await _inbox_item(session, item_id, current_user.id, manager=True)
    item.status = "rejected"
    item.decided_by = current_user.id
    item.decided_at = datetime.now(UTC)
    session.add(item)
    await session.commit()
    return {"status": "rejected"}


@router.post("/api/ai-inbox/{item_id}/edit")
async def edit_inbox(item_id: UUID, body: InboxEditRequest, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    item = await _inbox_item(session, item_id, current_user.id, manager=True)
    if body.parsed_payload is not None:
        item.parsed_payload = body.parsed_payload
        item.semantic_payload = body.parsed_payload
    if body.source_text is not None:
        item.source_text = body.source_text
        item.raw_text = body.source_text
    if body.proposed_action is not None:
        item.proposed_action = body.proposed_action
    session.add(item)
    await session.commit()
    return {"status": "edited"}


@router.post("/api/ai-inbox/{item_id}/link-task")
async def link_inbox(item_id: UUID, body: LinkTaskRequest, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    item = await _inbox_item(session, item_id, current_user.id, manager=True)
    task = await session.get(m.TaskModel, body.task_id)
    if task is None or task.team_id != item.team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    item.linked_task_id = task.id
    item.status = "linked"
    item.decided_by = current_user.id
    item.decided_at = datetime.now(UTC)
    session.add(item)
    await session.commit()
    return {"status": "linked", "task_id": str(task.id)}


@router.get("/api/teams/{team_id}/recommendations")
async def team_recommendations(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id)
    return await recommendations_for_team(session, team_id)


@router.get("/api/companies/{company_id}/recommendations")
async def company_recommendations(company_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    ctx = await build_tenant_context(current_user.id, session)
    require_company_role(ctx, company_id, "director")
    teams = (
        (
            await session.execute(select(m.TeamModel).where(m.TeamModel.company_id == company_id))
        )
        .scalars()
        .all()
    )
    items: list[dict[str, Any]] = []
    for team in teams:
        recs = await recommendations_for_team(session, team.id)
        items.extend({**item, "team_id": str(team.id), "team_name": team.name} for item in recs["items"])
    return {"items": items}


@router.post("/api/recommendations/{recommendation_id}/ignore")
async def ignore_recommendation(recommendation_id: str, current_user: CurrentUser) -> dict:
    del current_user
    return {"id": recommendation_id, "status": "ignored"}


@router.post("/api/recommendations/{recommendation_id}/apply")
async def apply_recommendation(recommendation_id: str, current_user: CurrentUser) -> dict:
    del current_user
    return {"id": recommendation_id, "status": "applied"}


@router.get("/api/teams/{team_id}/setup/status")
async def setup_status(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    team = await _require_team(session, current_user.id, team_id)
    members = int(await session.scalar(select(func.count()).select_from(m.TeamMemberModel).where(m.TeamMemberModel.team_id == team_id)) or 0)
    yg = await yougile_status(team_id, current_user, session)
    llm_ready = team.llm_settings_id is not None
    return {
        "steps": [
            {"key": "company", "title": "Company created", "status": "done"},
            {"key": "team", "title": "Team created", "status": "done"},
            {"key": "members", "title": "Participants", "status": "done" if members > 1 else "warning"},
            {"key": "telegram", "title": "Telegram linked", "status": "done" if team.tg_chat_id else "warning"},
            {"key": "yougile", "title": "YouGile connected", "status": "done" if yg["connected"] else "todo"},
            {"key": "board", "title": "Board imported", "status": "done" if yg["selected_board"] else "todo"},
            {"key": "llm", "title": "LLM ready", "status": "done" if llm_ready else "warning"},
            {"key": "demo", "title": "Test scenario", "status": "todo"},
        ]
    }


@router.post("/api/teams/{team_id}/setup/run-demo")
async def run_demo(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id, manager=True)
    existing = await session.scalar(select(m.TaskModel).where(m.TaskModel.team_id == team_id, m.TaskModel.title == "Demo: вечерний синк Grey Cardinal"))
    if existing is None:
        seq = int(await session.scalar(select(func.max(m.TaskModel.seq))) or 0) + 1
        session.add(
            m.TaskModel(
                id=uuid4(),
                seq=seq,
                public_id=f"GC-{seq}",
                team_id=team_id,
                title="Demo: вечерний синк Grey Cardinal",
                description="Проверочная задача setup wizard",
                status="todo",
                priority="medium",
                source="manual",
                source_type="manual",
                source_text="Setup Wizard demo",
            )
        )
    session.add(
        m.AiInboxItemModel(
            id=uuid4(),
            team_id=team_id,
            item_type="task_proposal",
            kind="task_proposal",
            status="pending",
            source_type="manual",
            source_text="Демо: агент предлагает запросить статус перед вечерним синком",
            reason="setup_wizard_demo",
            raw_text="Демо: агент предлагает запросить статус перед вечерним синком",
            confidence=0.91,
            proposed_action="ask_status",
            parsed_payload={"title": "Запросить статус у команды"},
            semantic_payload={"title": "Запросить статус у команды"},
        )
    )
    await session.commit()
    return {"ok": True}


@router.get("/api/companies/{company_id}/map")
async def company_map(company_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    ctx = await build_tenant_context(current_user.id, session)
    require_company_role(ctx, company_id, "director")
    return await company_map_payload(session, company_id)


@router.get("/api/teams/{team_id}/people")
async def people(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id)
    rows = (
        (
            await session.execute(
                select(m.UserModel, m.TeamMemberModel.role)
                .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
                .where(m.TeamMemberModel.team_id == team_id)
                .order_by(m.UserModel.display_name)
            )
        )
        .all()
    )
    items = []
    for user, role in rows:
        profile = await employee_profile_payload(session, user.id, team_id=team_id)
        items.append({"id": str(user.id), "display_name": user.display_name, "email": user.email, "role": role, "profile": profile})
    return {"items": items}


@router.get("/api/people/{user_id}/profile")
async def person_profile(user_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    ctx = await build_tenant_context(current_user.id, session)
    is_self = user_id == current_user.id
    if not is_self:
        member_team_ids = [tid for tid, role in ctx.team_roles.items() if role == "manager"]
        if not member_team_ids:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager role required")
    return await employee_profile_payload(session, user_id)


@router.get("/api/users/me/profile")
async def my_profile(current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    return await employee_profile_payload(session, current_user.id)


@router.get("/api/teams/{team_id}/telegram/topics")
async def telegram_topics(team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id)
    rows = (
        (
            await session.execute(
                select(m.TelegramChatModel, m.ChatMessageModel.message_thread_id, m.TelegramTopicBindingModel)
                .join(m.ChatMessageModel, m.ChatMessageModel.chat_id == m.TelegramChatModel.id)
                .outerjoin(
                    m.TelegramTopicBindingModel,
                    (m.TelegramTopicBindingModel.telegram_chat_id == m.TelegramChatModel.id)
                    & (m.TelegramTopicBindingModel.message_thread_id == m.ChatMessageModel.message_thread_id),
                )
                .where(m.TelegramChatModel.team_id == team_id, m.ChatMessageModel.message_thread_id.is_not(None))
                .distinct()
            )
        )
        .all()
    )
    return {"items": [_topic_payload(chat, thread_id, binding) for chat, thread_id, binding in rows]}


@router.post("/api/teams/{team_id}/telegram/topics")
async def bind_topic(team_id: UUID, body: TopicBindRequest, current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    await _require_team(session, current_user.id, team_id, manager=True)
    binding = await session.scalar(
        select(m.TelegramTopicBindingModel).where(
            m.TelegramTopicBindingModel.telegram_chat_id == body.telegram_chat_id,
            m.TelegramTopicBindingModel.message_thread_id == body.message_thread_id,
        )
    )
    if binding is None:
        binding = m.TelegramTopicBindingModel(
            id=uuid4(),
            telegram_chat_id=body.telegram_chat_id,
            message_thread_id=body.message_thread_id,
        )
    binding.team_id = team_id
    binding.board_id = body.board_id
    binding.source_name = body.source_name
    session.add(binding)
    await session.commit()
    return {"id": str(binding.id), "status": "bound"}


async def _inbox_item(
    session: AsyncSession,
    item_id: UUID,
    user_id: UUID,
    *,
    manager: bool,
) -> m.AiInboxItemModel:
    item = await session.get(m.AiInboxItemModel, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AI inbox item not found")
    await _require_team(session, user_id, item.team_id, manager=manager)
    return item


def _external_payload(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "external_id": row.external_id,
        "name": row.name,
        "raw_payload": row.raw_payload,
        "synced_at": row.synced_at,
    }


def _board_payload(row: m.YouGileBoardModel) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "external_id": row.external_id,
        "name": row.name,
        "project_id": str(row.project_id) if row.project_id else None,
        "is_selected": row.is_selected,
        "synced_at": row.synced_at,
    }


def _column_payload(row: m.YouGileColumnModel) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "external_id": row.external_id,
        "name": row.name,
        "mapped_status": row.mapped_status,
        "position": row.position,
    }


def _sync_event_payload(row: m.SyncEventModel) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "provider": row.provider,
        "direction": row.direction,
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id) if row.entity_id else None,
        "external_id": row.external_id,
        "status": row.status,
        "message": row.message,
        "payload": row.payload,
        "created_at": row.created_at,
    }


def _topic_payload(
    chat: m.TelegramChatModel,
    thread_id: int,
    binding: m.TelegramTopicBindingModel | None,
) -> dict[str, Any]:
    return {
        "telegram_chat_id": str(chat.id),
        "chat_title": chat.title,
        "message_thread_id": thread_id,
        "team_id": str(binding.team_id) if binding and binding.team_id else None,
        "board_id": str(binding.board_id) if binding and binding.board_id else None,
        "source_name": binding.source_name if binding else None,
        "bound": binding is not None,
    }
