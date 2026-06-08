"""Agentic Grey Board and AI Inbox endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.deps import get_container
from brain_api.api.rbac import build_tenant_context, require_team_member, require_team_role
from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.application.agentic_tasks import (
    AssigneeResolution,
    IdentityResolver,
    InteractionMode,
    TaskDecisionEngine,
)
from brain_api.application.semantic_parser import SemanticMessageInput
from brain_api.application.task_numbering import next_task_public_id
from brain_api.application.task_status_service import TaskStatusService
from brain_api.container import Container
from brain_api.domain.enums import TaskStatus
from brain_api.infrastructure.db import models as m

router = APIRouter(tags=["grey-board"])

DB_TASK_STATUSES = {"todo", "in_progress", "blocked", "review", "done", "cancelled"}


class MoveTaskRequest(BaseModel):
    status: TaskStatus


class AssignTaskRequest(BaseModel):
    user_id: UUID | None = None


_DEFAULT_KANBAN_COLUMNS = [
    {"status": "todo", "label": "К выполнению", "color": "#3a7afe", "visible": True},
    {"status": "in_progress", "label": "В работе", "color": "#f1c40f", "visible": True},
    {"status": "review", "label": "На проверке", "color": "#a06bff", "visible": True},
    {"status": "blocked", "label": "Заблокировано", "color": "#ff003c", "visible": False},
    {"status": "done", "label": "Готово", "color": "#2ecc71", "visible": True},
    {"status": "cancelled", "label": "Отменено", "color": "#6a6a73", "visible": False},
]


class KanbanColumn(BaseModel):
    status: str
    label: str
    color: str = "#6a6a73"
    visible: bool = True


class KanbanConfigRequest(BaseModel):
    columns: list[KanbanColumn]


class DeadlineRequest(BaseModel):
    deadline: datetime | None = None


class InboxAssignRequest(BaseModel):
    user_id: UUID


class InboxDuplicateRequest(BaseModel):
    task_id: UUID


class TaskCommandParseRequest(BaseModel):
    text: str


class TaskCommandConfirmRequest(BaseModel):
    title: str
    description: str | None = None
    assignee_id: UUID | None = None
    deadline: datetime | None = None
    priority: str = "medium"
    status: str | None = None


async def _team_access(
    team_id: UUID, current_user: CurrentUser, session: AsyncSession
) -> m.TeamModel:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_member(ctx, team_id)
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    return team


@router.get("/api/teams/{team_id}/grey-board")
async def grey_board(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
    view: str = "agent",
) -> dict[str, Any]:
    team = await _team_access(team_id, current_user, session)
    rows = (
        await session.execute(
            select(
                m.TaskModel,
                m.UserModel,
                m.ExternalTaskLinkModel,
                m.TaskProposalModel,
                m.ChatMessageModel,
            )
            .outerjoin(m.UserModel, m.UserModel.id == m.TaskModel.assignee_id)
            .outerjoin(
                m.ExternalTaskLinkModel,
                (m.ExternalTaskLinkModel.task_id == m.TaskModel.id)
                & (m.ExternalTaskLinkModel.provider == "yougile"),
            )
            .outerjoin(
                m.TaskProposalModel,
                m.TaskProposalModel.id == m.TaskModel.created_from_proposal_id,
            )
            .outerjoin(
                m.ChatMessageModel,
                m.ChatMessageModel.id == m.TaskModel.source_message_id,
            )
            .where(m.TaskModel.team_id == team_id)
            .order_by(m.TaskModel.seq)
        )
    ).all()
    cards = [
        _task_card(task, user, link, proposal, source_message, team.timezone)
        for task, user, link, proposal, source_message in rows
    ]
    columns = _group_cards(view, cards)
    pending_inbox = []
    if view == "agent":
        inbox_rows = list(
            await session.scalars(
                select(m.AIInboxItemModel)
                .where(
                    m.AIInboxItemModel.team_id == team_id,
                    m.AIInboxItemModel.status == "pending",
                )
                .order_by(m.AIInboxItemModel.created_at.desc())
                .limit(100)
            )
        )
        pending_inbox = [_inbox_card(item) for item in inbox_rows]
        columns.insert(0, ("ai_inbox", "AI Inbox", pending_inbox))
    sync_error_count = sum(card["sync"]["status"] in {"error", "conflict"} for card in cards)
    overdue_count = sum(card["risk"]["overdue"] for card in cards)
    risk_count = sum(
        card["risk"]["overdue"]
        or card["risk"]["due_soon"]
        or card["risk"]["unassigned"]
        or card["risk"]["stale"]
        or card["sync"]["status"] in {"error", "conflict"}
        for card in cards
    )
    last_sync_at = await session.scalar(
        select(func.max(m.SyncEventModel.created_at)).where(m.SyncEventModel.team_id == team_id)
    )
    latest_sync_error = await session.scalar(
        select(m.SyncEventModel)
        .where(m.SyncEventModel.team_id == team_id, m.SyncEventModel.status == "error")
        .order_by(m.SyncEventModel.created_at.desc())
        .limit(1)
    )
    selected_board = await session.scalar(
        select(m.YouGileBoardModel).where(
            m.YouGileBoardModel.team_id == team_id,
            m.YouGileBoardModel.is_selected.is_(True),
        )
    )
    yougile_health = "unconfigured"
    if selected_board is not None:
        yougile_health = "error" if latest_sync_error else "synced"
    elif team.board_credentials_encrypted:
        yougile_health = "pending"
    board_columns = [
        {"id": key, "title": title, "cards": items, "tasks": items}
        for key, title, items in columns
    ]
    return {
        "team_id": str(team_id),
        "view": view,
        "generated_at": datetime.now(UTC),
        "health": {
            "llm": "ok" if team.llm_settings_id else "warning",
            "telegram": "linked" if team.tg_chat_id else "unlinked",
            "yougile": yougile_health,
            "last_sync_at": last_sync_at,
            "open_risks": risk_count,
            "latest_error": latest_sync_error.error if latest_sync_error else None,
        },
        "stats": {
            "tasks": len(cards),
            "overdue": overdue_count,
            "risks": risk_count,
            "sync_errors": sync_error_count,
            "ai_inbox": len(pending_inbox),
        },
        # `tasks` and `groups` keep already-open clients compatible while the
        # current frontend uses `columns[].cards`.
        "columns": board_columns,
        "groups": board_columns,
        "recommendations": [],
    }


@router.post("/api/tasks/{task_id}/move")
async def move_task(
    task_id: UUID,
    body: MoveTaskRequest,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if body.status.value not in DB_TASK_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported task status")
    task = await session.get(m.TaskModel, task_id)
    if task is None or task.team_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await _team_access(task.team_id, current_user, session)
    result = await TaskStatusService(container.board_mirror).update_status(
        task_id,
        body.status,
        actor_id=current_user.id,
        action="grey_board_status_changed",
    )
    return {
        "task_id": str(task_id),
        "status": result.status,
        "sync_status": result.sync_status,
        "sync_error": result.sync_error,
    }


@router.post("/api/tasks/{task_id}/assign")
async def assign_task(
    task_id: UUID,
    body: AssignTaskRequest,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    task = await session.get(m.TaskModel, task_id)
    if task is None or task.team_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, task.team_id, "manager")
    user = None
    if body.user_id:
        user = await session.scalar(
            select(m.UserModel)
            .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
            .where(
                m.TeamMemberModel.team_id == task.team_id,
                m.UserModel.id == body.user_id,
            )
        )
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Team member not found")
    task.assignee_id = user.id if user else None
    task.assignee_text = user.display_name if user else None
    link = await session.scalar(
        select(m.ExternalTaskLinkModel).where(m.ExternalTaskLinkModel.task_id == task.id)
    )
    if link:
        link.sync_status = "pending_update"
    await session.commit()
    sync = await container.board_mirror.sync_task_fields(task.id)
    await container.websocket_manager.broadcast(
        {
            "event": "task_assigned",
            "payload": {
                "task_id": str(task.id),
                "public_id": task.public_id,
                "title": task.title,
                "team_id": str(task.team_id),
                "assignee_id": str(user.id) if user else None,
                "assignee_name": user.display_name if user else None,
                "actor_id": str(current_user.id),
            },
        }
    )
    return {
        "task_id": str(task.id),
        "assignee": _user_payload(user),
        "sync_status": sync.sync_status,
        "sync_error": sync.error,
    }


@router.post("/api/tasks/{task_id}/deadline")
async def set_deadline(
    task_id: UUID,
    body: DeadlineRequest,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    task = await session.get(m.TaskModel, task_id)
    if task is None or task.team_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await _team_access(task.team_id, current_user, session)
    task.deadline = body.deadline
    link = await session.scalar(
        select(m.ExternalTaskLinkModel).where(m.ExternalTaskLinkModel.task_id == task.id)
    )
    if link:
        link.sync_status = "pending_update"
    await session.commit()
    sync = await container.board_mirror.sync_task_fields(task.id)
    return {
        "task_id": str(task.id),
        "deadline": task.deadline,
        "sync_status": sync.sync_status,
        "sync_error": sync.error,
    }


@router.post("/api/tasks/{task_id}/ask-status")
async def ask_status(
    task_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    task = await session.get(m.TaskModel, task_id)
    if task is None or task.team_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await _team_access(task.team_id, current_user, session)
    session.add(
        m.AuditLogModel(
            actor_type="user",
            actor_id=str(current_user.id),
            action="task_status_requested",
            entity_type="task",
            entity_id=task.id,
            payload={"public_id": task.public_id},
        )
    )
    await session.commit()
    return {"queued": True, "task_id": str(task.id)}


class CommentBody(BaseModel):
    body: str


def _comment_payload(c: m.TaskCommentModel) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "body": c.body,
        "author_id": str(c.author_id) if c.author_id else None,
        "author_name": c.author_name,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/api/tasks/{task_id}/comments")
async def list_comments(
    task_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    task = await session.get(m.TaskModel, task_id)
    if task is None or task.team_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await _team_access(task.team_id, current_user, session)
    rows = list(
        await session.scalars(
            select(m.TaskCommentModel)
            .where(m.TaskCommentModel.task_id == task_id)
            .order_by(m.TaskCommentModel.created_at.asc())
            .limit(500)
        )
    )
    return {"items": [_comment_payload(c) for c in rows]}


@router.post("/api/tasks/{task_id}/comments")
async def add_comment(
    task_id: UUID,
    body: CommentBody,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    text = (body.body or "").strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty comment")
    task = await session.get(m.TaskModel, task_id)
    if task is None or task.team_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await _team_access(task.team_id, current_user, session)
    comment = m.TaskCommentModel(
        task_id=task_id,
        author_id=current_user.id,
        author_name=current_user.display_name,
        body=text[:4000],
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return _comment_payload(comment)


@router.get("/api/teams/{team_id}/kanban-config")
async def get_kanban_config(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _team_access(team_id, current_user, session)
    team = await session.get(m.TeamModel, team_id)
    columns = (team.board_config or {}).get("kanban_columns") if team else None
    return {"columns": columns or _DEFAULT_KANBAN_COLUMNS}


@router.put("/api/teams/{team_id}/kanban-config")
async def put_kanban_config(
    team_id: UUID,
    body: KanbanConfigRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, team_id, "manager")
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for col in body.columns:
        if col.status not in DB_TASK_STATUSES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid status {col.status}")
        if col.status in seen:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Duplicate status {col.status}")
        seen.add(col.status)
        cleaned.append({
            "status": col.status,
            "label": col.label.strip()[:40] or col.status,
            "color": col.color[:9],
            "visible": bool(col.visible),
        })
    if not any(c["visible"] for c in cleaned):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one column must be visible")
    team = await session.get(m.TeamModel, team_id)
    config = dict(team.board_config or {})
    config["kanban_columns"] = cleaned
    team.board_config = config
    await session.commit()
    return {"columns": cleaned}


@router.get("/api/teams/{team_id}/ai-inbox")
async def ai_inbox(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _team_access(team_id, current_user, session)
    await _sync_daemon_proposals_to_inbox(session, team_id)
    rows = list(
        await session.scalars(
            select(m.AIInboxItemModel)
            .where(m.AIInboxItemModel.team_id == team_id)
            .order_by(m.AIInboxItemModel.created_at.desc())
            .limit(200)
        )
    )
    return {"items": [_inbox_payload(item) for item in rows]}


async def _sync_daemon_proposals_to_inbox(session: AsyncSession, team_id: UUID) -> None:
    """Expose old/new Windows-agent confirmations in the website AI Inbox."""
    rows = (
        await session.execute(
            select(m.TaskProposalModel, m.ConfirmationModel)
            .join(
                m.ConfirmationModel,
                m.ConfirmationModel.proposal_id == m.TaskProposalModel.id,
            )
            .where(
                m.TaskProposalModel.team_id == team_id,
                m.TaskProposalModel.source == "meeting_transcript",
            )
        )
    ).all()
    existing = {
        item.source_id: item
        for item in (
            await session.scalars(
                select(m.AIInboxItemModel).where(
                    m.AIInboxItemModel.team_id == team_id,
                    m.AIInboxItemModel.source_type == "daemon_proposal",
                )
            )
        )
    }
    changed = False
    for proposal, confirmation in rows:
        source_id = str(proposal.id)
        item = existing.get(source_id)
        if item is None and confirmation.status == "pending":
            identity = {
                "status": "resolved" if proposal.assignee_id else "unresolved",
                "user_id": str(proposal.assignee_id) if proposal.assignee_id else None,
                "display_name": proposal.assignee_text,
                "source": "proposal",
                "confidence": proposal.confidence,
                "candidates": [],
                "raw_reference": proposal.assignee_text,
            }
            session.add(
                m.AIInboxItemModel(
                    team_id=team_id,
                    kind="task_candidate",
                    status="pending",
                    reason="windows_agent_proposal",
                    raw_text=proposal.raw_text,
                    semantic_payload=proposal.extractor_payload,
                    identity_payload=identity,
                    item_type="task_proposal",
                    source_type="daemon_proposal",
                    source_id=source_id,
                    source_text=proposal.raw_text,
                    proposed_action="approve",
                    confidence=proposal.confidence,
                )
            )
            changed = True
        elif item is not None and confirmation.status in {"accepted", "rejected", "expired"}:
            expected = "approved" if confirmation.status == "accepted" else confirmation.status
            if item.status != expected or item.linked_task_id != confirmation.created_task_id:
                item.status = expected
                item.linked_task_id = confirmation.created_task_id
                changed = True
    if changed:
        await session.commit()


@router.post("/api/ai-inbox/{item_id}/approve")
async def approve_inbox(
    item_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    item = await session.get(m.AIInboxItemModel, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inbox item not found")
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, item.team_id, "manager")
    if item.status == "approved" and item.linked_task_id:
        task = await session.get(m.TaskModel, item.linked_task_id)
        if task is not None:
            return {
                "task_id": str(task.id),
                "public_id": task.public_id,
                "sync_status": "local_only",
            }
    semantic = item.semantic_payload or {}
    payload = semantic.get("task") or {}
    identity = item.identity_payload or {}
    assignee_id = UUID(identity["user_id"]) if identity.get("user_id") else None
    proposal = None
    if item.source_type == "daemon_proposal" and item.source_id:
        try:
            proposal_id = UUID(item.source_id)
        except ValueError:
            proposal_id = None
        if proposal_id:
            proposal = await session.get(m.TaskProposalModel, proposal_id)
            existing = await session.scalar(
                select(m.TaskModel).where(m.TaskModel.created_from_proposal_id == proposal_id)
            )
            if existing is not None:
                item.status = "approved"
                item.linked_task_id = existing.id
                item.decided_by = current_user.id
                item.decided_at = datetime.now(UTC)
                await session.commit()
                return {
                    "task_id": str(existing.id),
                    "public_id": existing.public_id,
                    "sync_status": "local_only",
                }
    task = await _create_task_row(
        session,
        team_id=item.team_id,
        title=proposal.title if proposal else str(
            payload.get("title") or (item.raw_text or item.source_text or "")[:120]
        ),
        description=proposal.description if proposal else payload.get("description"),
        assignee_id=assignee_id if assignee_id else (proposal.assignee_id if proposal else None),
        assignee_text=identity.get("display_name")
        or (proposal.assignee_text if proposal else None),
        deadline=proposal.deadline if proposal else _parse_dt(payload.get("deadline")),
        priority=proposal.priority if proposal else str(payload.get("priority") or "medium"),
        source_message_id=item.source_message_id,
        source=proposal.source if proposal else "telegram_chat",
        created_from_proposal_id=proposal.id if proposal else None,
    )
    item.status = "approved"
    item.linked_task_id = task.id
    item.decided_by = current_user.id
    item.decided_at = datetime.now(UTC)
    if proposal is not None:
        confirmation = await session.scalar(
            select(m.ConfirmationModel).where(m.ConfirmationModel.proposal_id == proposal.id)
        )
        if confirmation is not None:
            confirmation.status = "accepted"
            confirmation.created_task_id = task.id
    await session.commit()
    return {
        "task_id": str(task.id),
        "public_id": task.public_id,
        "sync_status": "local_only",
    }


@router.post("/api/ai-inbox/{item_id}/reject")
async def reject_inbox(
    item_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    item = await session.get(m.AIInboxItemModel, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inbox item not found")
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, item.team_id, "manager")
    item.status = "rejected"
    item.decided_by = current_user.id
    item.decided_at = datetime.now(UTC)
    if item.source_type == "daemon_proposal" and item.source_id:
        try:
            proposal_id = UUID(item.source_id)
        except ValueError:
            proposal_id = None
        if proposal_id:
            confirmation = await session.scalar(
                select(m.ConfirmationModel).where(m.ConfirmationModel.proposal_id == proposal_id)
            )
            if confirmation is not None and confirmation.status == "pending":
                confirmation.status = "rejected"
    await session.commit()
    return {"status": item.status}


@router.post("/api/ai-inbox/{item_id}/assign")
async def assign_inbox(
    item_id: UUID,
    body: InboxAssignRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    item = await session.get(m.AIInboxItemModel, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inbox item not found")
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, item.team_id, "manager")
    user = await session.scalar(
        select(m.UserModel)
        .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
        .where(
            m.TeamMemberModel.team_id == item.team_id,
            m.UserModel.id == body.user_id,
        )
    )
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team member not found")
    item.identity_payload = AssigneeResolution(
        status="resolved",
        user_id=user.id,
        display_name=user.display_name,
        source="manual",
        confidence=1.0,
    ).payload()
    item.kind = "task_candidate_uncertain"
    if item.source_type == "daemon_proposal" and item.source_id:
        try:
            proposal_id = UUID(item.source_id)
        except ValueError:
            proposal_id = None
        if proposal_id:
            proposal = await session.get(m.TaskProposalModel, proposal_id)
            if proposal is not None:
                proposal.assignee_id = user.id
                proposal.assignee_text = user.display_name
    await session.commit()
    return {"assignee": _user_payload(user)}


@router.post("/api/ai-inbox/{item_id}/link-duplicate")
async def link_inbox_duplicate(
    item_id: UUID,
    body: InboxDuplicateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    item = await session.get(m.AIInboxItemModel, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inbox item not found")
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, item.team_id, "manager")
    task = await session.get(m.TaskModel, body.task_id)
    if task is None or task.team_id != item.team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    item.duplicate_task_id = task.id
    item.status = "resolved"
    await session.commit()
    return {"linked_task_id": str(task.id), "status": item.status}


@router.post("/api/teams/{team_id}/task-command/parse")
async def parse_task_command(
    team_id: UUID,
    body: TaskCommandParseRequest,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    team = await _team_access(team_id, current_user, session)
    members = list(
        await session.scalars(
            select(m.UserModel)
            .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
            .where(m.TeamMemberModel.team_id == team_id)
        )
    )
    parsed = await container.semantic_parser.parse(
        SemanticMessageInput(
            team_id=team_id,
            message_text=body.text,
            sender_user_id=current_user.id,
            team_timezone=team.timezone,
            now=datetime.now(UTC),
            sender_display_name=current_user.display_name,
            team_members=[user.display_name for user in members],
            interaction_mode=InteractionMode.WEB_MANUAL.value,
        )
    )
    task_payload = parsed.get("task") or {}
    resolution = await IdentityResolver(session).resolve_assignee(
        team_id,
        task_payload.get("assignee_reference") or task_payload.get("assignee_text"),
        [],
        body.text,
        None,
        InteractionMode.WEB_MANUAL,
    )
    decision = TaskDecisionEngine().decide(
        semantic_result=parsed,
        identity_resolution=resolution,
        interaction_mode=InteractionMode.WEB_MANUAL,
        has_context=False,
    )
    return {
        "semantic": parsed,
        "identity": resolution.payload(),
        "decision": {
            "action": decision.action,
            "reason": decision.reason,
            "confidence": decision.confidence,
        },
    }


@router.post("/api/teams/{team_id}/task-command/confirm")
async def confirm_web_task(
    team_id: UUID,
    body: TaskCommandConfirmRequest,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _team_access(team_id, current_user, session)
    status_value = body.status if body.status in DB_TASK_STATUSES else "todo"
    task = await _create_task_row(
        session,
        team_id=team_id,
        title=body.title,
        description=body.description,
        assignee_id=body.assignee_id,
        deadline=body.deadline,
        priority=body.priority,
        source_message_id=None,
        source="manual",
        status=status_value,
    )
    await session.commit()
    sync = await container.board_mirror.create_external_task(task.id)
    return {
        "task_id": str(task.id),
        "public_id": task.public_id,
        "sync_status": sync.sync_status,
    }


async def _create_task_row(
    session: AsyncSession,
    *,
    team_id: UUID,
    title: str,
    description: str | None,
    assignee_id: UUID | None,
    deadline: datetime | None,
    priority: str,
    source_message_id: UUID | None,
    source: str,
    assignee_text: str | None = None,
    created_from_proposal_id: UUID | None = None,
    status: str = "todo",
) -> m.TaskModel:
    seq, public_id = await next_task_public_id(session, team_id)
    assignee = await session.get(m.UserModel, assignee_id) if assignee_id else None
    task = m.TaskModel(
        seq=seq,
        public_id=public_id,
        team_id=team_id,
        title=title,
        description=description,
        status=status if status in DB_TASK_STATUSES else "todo",
        priority=priority if priority in {"low", "medium", "high", "critical"} else "medium",
        assignee_id=assignee_id,
        assignee_text=assignee.display_name if assignee else assignee_text,
        deadline=deadline,
        source=source,
        source_message_id=source_message_id,
        created_from_proposal_id=created_from_proposal_id,
    )
    session.add(task)
    await session.flush()
    return task


def _task_card(
    task: m.TaskModel,
    user: m.UserModel | None,
    link: m.ExternalTaskLinkModel | None,
    proposal: m.TaskProposalModel | None,
    source_message: m.ChatMessageModel | None,
    timezone: str,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    deadline = task.deadline
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    overdue = bool(deadline and deadline < now and task.status not in {"done", "cancelled"})
    soon = bool(deadline and now <= deadline <= now + timedelta(hours=24))
    updated = task.last_status_update_at or task.updated_at
    if updated and updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return {
        "id": str(task.id),
        "public_id": task.public_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "assignee": _user_payload(user),
        "deadline": task.deadline,
        "timezone": timezone,
        "source": task.source,
        "confidence": proposal.confidence if proposal else None,
        "evidence": {
            "raw_text": (
                proposal.raw_text
                if proposal
                else (source_message.text if source_message else None)
            ),
            "source_message_id": str(source_message.id) if source_message else None,
            "telegram_message_id": source_message.telegram_message_id if source_message else None,
        },
        "agent": {
            "semantic": proposal.extractor_payload if proposal else None,
            "identity_resolution": (
                (proposal.extractor_payload or {}).get("identity_resolution")
                if proposal
                else None
            ),
        },
        "sync": {
            "status": link.sync_status if link else "local_only",
            "error": link.last_error if link else None,
            "external_task_id": link.external_task_id if link else None,
            "external_board_id": link.external_board_id if link else None,
            "external_column_id": link.external_column_id if link else None,
            "external_url": link.external_url if link else None,
        },
        "risk": {
            "overdue": overdue,
            "due_soon": soon,
            "unassigned": task.assignee_id is None,
            "stale": bool(updated and updated < now - timedelta(hours=24)),
        },
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _group_cards(view: str, cards: list[dict[str, Any]]):
    if view == "status":
        spec = [
            ("todo", "Todo"),
            ("in_progress", "In Progress"),
            ("blocked", "Blocked"),
            ("review", "Review"),
            ("done", "Done"),
        ]
        return [
            (key, title, [card for card in cards if card["status"] == key])
            for key, title in spec
        ]
    if view == "people":
        assignees = sorted(
            {
                (card["assignee"]["id"], card["assignee"]["display_name"])
                for card in cards
                if card["assignee"]
            },
            key=lambda item: item[1].lower(),
        )
        result = [
            (
                user_id,
                display_name,
                [
                    card
                    for card in cards
                    if card["assignee"]
                    and card["assignee"]["id"] == user_id
                ],
            )
            for user_id, display_name in assignees
        ]
        result.append(
            ("unassigned", "Без исполнителя", [card for card in cards if not card["assignee"]])
        )
        return result
    if view == "risk":
        return [
            ("overdue", "Просрочено", [card for card in cards if card["risk"]["overdue"]]),
            (
                "due_soon",
                "Скоро дедлайн",
                [card for card in cards if card["risk"]["due_soon"]],
            ),
            ("stale", "Нет статуса", [card for card in cards if card["risk"]["stale"]]),
            (
                "sync",
                "Sync errors",
                [
                    card
                    for card in cards
                    if card["sync"]["status"] in {"error", "conflict"}
                ],
            ),
        ]
    if view == "timeline":
        now = datetime.now(UTC)
        return [
            ("today", "Сегодня", [card for card in cards if _deadline_day(card, now, 0)]),
            ("tomorrow", "Завтра", [card for card in cards if _deadline_day(card, now, 1)]),
            (
                "week",
                "На неделе",
                [card for card in cards if _deadline_within(card, now, 2, 7)],
            ),
            ("none", "Без дедлайна", [card for card in cards if not card["deadline"]]),
            ("overdue", "Просрочено", [card for card in cards if card["risk"]["overdue"]]),
        ]
    if view == "source":
        sources = [
            ("telegram_chat", "Telegram"),
            ("meeting_transcript", "Meeting"),
            ("yougile_import", "YouGile import"),
            ("daily_sync", "Daily sync"),
            ("manual", "Manual"),
        ]
        return [
            (key, title, [card for card in cards if card["source"] == key])
            for key, title in sources
        ]
    return [
        (
            "needs_decision",
            "Нужно решение",
            [
                card
                for card in cards
                if card["risk"]["unassigned"] or card["sync"]["status"] == "conflict"
            ],
        ),
        (
            "active",
            "Активные",
            [
                card
                for card in cards
                if card["status"] in {"todo", "in_progress", "review"}
            ],
        ),
        ("waiting", "Ждём статус", [card for card in cards if card["risk"]["stale"]]),
        (
            "risks",
            "Риски",
            [
                card
                for card in cards
                if card["risk"]["overdue"]
                or card["sync"]["status"] in {"error", "conflict"}
            ],
        ),
        ("done", "Готово", [card for card in cards if card["status"] == "done"]),
    ]


def _user_payload(user: m.UserModel | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "telegram_username": user.telegram_username,
        "telegram_user_id": user.telegram_user_id,
        "photo_data_url": user.photo_data_url,
    }


def _inbox_payload(item: m.AIInboxItemModel) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "kind": item.kind or item.item_type or "task_candidate_uncertain",
        "status": item.status,
        "reason": item.reason,
        "raw_text": item.raw_text or item.source_text,
        "semantic": item.semantic_payload,
        "identity": item.identity_payload,
        "duplicate_task_id": (
            str(item.duplicate_task_id) if item.duplicate_task_id else None
        ),
        "confidence": item.confidence,
        "created_at": item.created_at,
        "source": {
            "type": item.source_type or "telegram",
            "message_id": str(item.source_message_id) if item.source_message_id else item.source_id,
        },
        "suggested_action": item.proposed_action or _suggested_action(item),
    }


def _suggested_action(item: m.AIInboxItemModel) -> str:
    if item.kind in {"needs_assignee", "task_candidate_uncertain"}:
        return "choose_assignee"
    if item.duplicate_task_id:
        return "link_duplicate"
    return "review"


def _inbox_card(item: m.AIInboxItemModel) -> dict[str, Any]:
    payload = _inbox_payload(item)
    semantic_task = (item.semantic_payload or {}).get("task") or {}
    return {
        **payload,
        "public_id": "AI",
        "title": semantic_task.get("title") or (item.raw_text or item.source_text or "")[:120],
        "description": semantic_task.get("description"),
        "is_inbox": True,
    }


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _deadline_day(card: dict[str, Any], now: datetime, offset: int) -> bool:
    deadline = card["deadline"]
    return bool(deadline and (deadline.date() - now.date()).days == offset)


def _deadline_within(card: dict[str, Any], now: datetime, start: int, end: int) -> bool:
    deadline = card["deadline"]
    if not deadline:
        return False
    days = (deadline.date() - now.date()).days
    return start <= days <= end
