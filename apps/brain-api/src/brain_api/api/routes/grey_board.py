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
from brain_api.container import Container
from brain_api.domain.enums import TaskStatus
from brain_api.infrastructure.db import models as m

router = APIRouter(tags=["grey-board"])


class MoveTaskRequest(BaseModel):
    status: TaskStatus


class AssignTaskRequest(BaseModel):
    user_id: UUID | None = None


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
    return {
        "team_id": str(team_id),
        "view": view,
        "generated_at": datetime.now(UTC),
        "columns": [
            {"key": key, "title": title, "tasks": items} for key, title, items in columns
        ],
        "stats": {
            "tasks": len(cards),
            "ai_inbox": len(pending_inbox),
            "sync_errors": sum(
                card["sync"]["status"] in {"error", "conflict"} for card in cards
            ),
            "overdue": sum(card["risk"]["overdue"] for card in cards),
        },
    }


@router.post("/api/tasks/{task_id}/move")
async def move_task(
    task_id: UUID,
    body: MoveTaskRequest,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    task = await session.get(m.TaskModel, task_id)
    if task is None or task.team_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await _team_access(task.team_id, current_user, session)
    result = await container.board_mirror.move_task(task_id, body.status)
    return {
        "task_id": str(task_id),
        "status": body.status.value,
        "sync_status": result.sync_status,
        "sync_error": result.error,
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


@router.get("/api/teams/{team_id}/ai-inbox")
async def ai_inbox(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _team_access(team_id, current_user, session)
    rows = list(
        await session.scalars(
            select(m.AIInboxItemModel)
            .where(m.AIInboxItemModel.team_id == team_id)
            .order_by(m.AIInboxItemModel.created_at.desc())
            .limit(200)
        )
    )
    return [_inbox_payload(item) for item in rows]


@router.post("/api/ai-inbox/{item_id}/approve")
async def approve_inbox(
    item_id: UUID,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    item = await session.get(m.AIInboxItemModel, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inbox item not found")
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, item.team_id, "manager")
    semantic = item.semantic_payload or {}
    payload = semantic.get("task") or {}
    identity = item.identity_payload or {}
    assignee_id = UUID(identity["user_id"]) if identity.get("user_id") else None
    task = await _create_task_row(
        session,
        team_id=item.team_id,
        title=str(payload.get("title") or item.raw_text[:120]),
        description=payload.get("description"),
        assignee_id=assignee_id,
        deadline=_parse_dt(payload.get("deadline")),
        priority=str(payload.get("priority") or "medium"),
        source_message_id=item.source_message_id,
        source="telegram_chat",
    )
    item.status = "approved"
    await session.commit()
    sync = await container.board_mirror.create_external_task(task.id)
    return {
        "task_id": str(task.id),
        "public_id": task.public_id,
        "sync_status": sync.sync_status,
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
) -> m.TaskModel:
    seq = int(await session.scalar(select(func.max(m.TaskModel.seq))) or 0) + 1
    assignee = await session.get(m.UserModel, assignee_id) if assignee_id else None
    task = m.TaskModel(
        seq=seq,
        public_id=f"GC-{seq}",
        team_id=team_id,
        title=title,
        description=description,
        status="todo",
        priority=priority if priority in {"low", "medium", "high", "critical"} else "medium",
        assignee_id=assignee_id,
        assignee_text=assignee.display_name if assignee else None,
        deadline=deadline,
        source=source,
        source_message_id=source_message_id,
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
            ("backlog", "Backlog"),
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
        names = sorted(
            {card["assignee"]["display_name"] for card in cards if card["assignee"]}
        )
        result = [
            (
                name,
                name,
                [
                    card
                    for card in cards
                    if card["assignee"]
                    and card["assignee"]["display_name"] == name
                ],
            )
            for name in names
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
    }


def _inbox_payload(item: m.AIInboxItemModel) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "kind": item.kind,
        "status": item.status,
        "reason": item.reason,
        "raw_text": item.raw_text,
        "semantic": item.semantic_payload,
        "identity": item.identity_payload,
        "duplicate_task_id": (
            str(item.duplicate_task_id) if item.duplicate_task_id else None
        ),
        "confidence": item.confidence,
        "created_at": item.created_at,
    }


def _inbox_card(item: m.AIInboxItemModel) -> dict[str, Any]:
    payload = _inbox_payload(item)
    semantic_task = (item.semantic_payload or {}).get("task") or {}
    return {
        **payload,
        "public_id": "AI",
        "title": semantic_task.get("title") or item.raw_text[:120],
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
