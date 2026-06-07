"""Inbound YouGile webhook synchronization."""

from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.deps import get_container
from brain_api.api.routes.accounts import get_db
from brain_api.application.use_cases.team_gamification import TASK_COMPLETED_XP, grant_team_xp
from brain_api.container import Container
from brain_api.infrastructure.board.yougile import was_recent_outbound
from brain_api.infrastructure.db import models as m
from brain_api.integrations.yougile import YouGileMappingRepo
from grey_cardinal_contracts import EventName, WebsocketEvent

router = APIRouter(prefix="/api/integrations/yougile", tags=["yougile-webhooks"])

_WINDOW_SECONDS = 60.0
_EVENTS_PER_WINDOW = 100
_received_at: dict[UUID, deque[float]] = defaultdict(deque)


def _check_rate_limit(team_id: UUID) -> None:
    now = time.monotonic()
    bucket = _received_at[team_id]
    while bucket and bucket[0] <= now - _WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= _EVENTS_PER_WINDOW:
        retry_after = max(1, int(_WINDOW_SECONDS - (now - bucket[0])))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "webhook rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)


@router.post("/webhook/{team_id}", status_code=status.HTTP_202_ACCEPTED)
async def receive_yougile_webhook(
    team_id: UUID,
    payload: dict[str, Any],
    event: str = Query(default=""),
    secret: str = Query(default=""),
    signature: str = Header(default="", alias="X-YouGile-Signature"),
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")

    config = dict(team.board_config or {})
    expected = str(config.get("webhook_secret") or "")
    supplied = signature or secret
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        YouGileMappingRepo(session, team_id).log(
            direction="inbound",
            event="webhook-rejected",
            error="invalid webhook secret",
        )
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid webhook secret")

    _check_rate_limit(team_id)
    event_name = event or str(payload.get("event") or payload.get("type") or "")
    task_data = _task_payload(payload)
    yougile_id = str(task_data.get("id") or payload.get("id") or "")
    if not event_name.startswith("task-") or not yougile_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unsupported webhook payload")

    if was_recent_outbound(team_id, yougile_id):
        return {"accepted": True, "ignored": "outbound_echo"}

    repo = YouGileMappingRepo(session, team_id)
    link = await session.scalar(
        select(m.ExternalTaskLinkModel).where(
            m.ExternalTaskLinkModel.provider == "yougile",
            m.ExternalTaskLinkModel.external_task_id == yougile_id,
        )
    )
    if link is not None and link.team_id != team_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "external task is already linked to another team",
        )
    mapping = await repo.find_by_yougile("task", yougile_id)
    local_id = link.task_id if link is not None else mapping.local_id if mapping else None
    task = await session.get(m.TaskModel, local_id) if local_id else None
    created = task is None
    if task is None:
        task = await _create_local_task(session, team_id, config, task_data)

    was_done = task.status == "done"
    _apply_task_payload(task, config, task_data, event_name)
    if "assigned" in task_data:
        task.assignee_id = await _local_assignee(session, team_id, task_data)
    if task.status == "done" and not was_done:
        await grant_team_xp(
            session,
            user_id=task.assignee_id,
            team_id=team_id,
            task_id=task.id,
            kind="task_completed",
            points=TASK_COMPLETED_XP,
            reason=f"Закрыл задачу {task.public_id} в YouGile",
            idempotency_key=f"task_completed:{task.id}",
        )
    link = await _upsert_external_link(
        session,
        team_id=team_id,
        task=task,
        link=link,
        config=config,
        data=task_data,
        yougile_id=yougile_id,
    )
    await repo.upsert("task", yougile_id, local_id=task.id, payload=task_data)
    repo.log(
        direction="inbound",
        event=event_name,
        entity_type="task",
        yougile_id=yougile_id,
        local_id=task.id,
        payload=task_data,
    )
    session.add(task)
    await session.commit()

    ws_name = EventName.task_created if created else EventName.task_status_changed
    await container.event_publisher.publish(
        WebsocketEvent(
            event=ws_name,
            payload={
                "team_id": str(team_id),
                "task_id": str(task.id),
                "yougile_id": yougile_id,
                "status": task.status,
                "source": "yougile",
            },
        )
    )
    return {"accepted": True, "task_id": str(task.id)}


def _task_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "payload", "object", "task"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


async def _create_local_task(
    session: AsyncSession,
    team_id: UUID,
    config: dict[str, Any],
    data: dict[str, Any],
) -> m.TaskModel:
    seq = int(await session.scalar(select(func.max(m.TaskModel.seq))) or 0) + 1
    task = m.TaskModel(
        id=uuid4(),
        seq=seq,
        public_id=f"GC-{seq}",
        team_id=team_id,
        title=str(data.get("title") or "YouGile task"),
        description=data.get("description"),
        status=_status_for(config, data, "todo"),
        priority="medium",
        assignee_id=await _local_assignee(session, team_id, data),
        deadline=_deadline_from_yougile(data.get("deadline")),
        source="yougile_import",
        last_status_update_at=datetime.now(UTC),
    )
    session.add(task)
    return task


async def _upsert_external_link(
    session: AsyncSession,
    *,
    team_id: UUID,
    task: m.TaskModel,
    link: m.ExternalTaskLinkModel | None,
    config: dict[str, Any],
    data: dict[str, Any],
    yougile_id: str,
) -> m.ExternalTaskLinkModel:
    now = datetime.now(UTC)
    board_id = str(data.get("boardId") or config.get("default_board_id") or "")
    if not board_id:
        selected_board = await session.scalar(
            select(m.YouGileBoardModel).where(
                m.YouGileBoardModel.team_id == team_id,
                m.YouGileBoardModel.is_selected.is_(True),
            )
        )
        board_id = selected_board.external_id if selected_board else ""
    if link is None:
        link = m.ExternalTaskLinkModel(
            team_id=team_id,
            task_id=task.id,
            provider="yougile",
            external_board_id=board_id,
            external_task_id=yougile_id,
        )
        session.add(link)
    else:
        link.task_id = task.id
        if board_id:
            link.external_board_id = board_id
    link.external_column_id = str(data.get("columnId") or "") or link.external_column_id
    link.sync_status = "synced"
    link.last_error = None
    link.last_synced_at = now
    link.raw_payload = data
    return link


def _apply_task_payload(
    task: m.TaskModel,
    config: dict[str, Any],
    data: dict[str, Any],
    event_name: str,
) -> None:
    if data.get("title"):
        task.title = str(data["title"])
    if "description" in data:
        task.description = data.get("description")
    if event_name == "task-deleted" or data.get("deleted"):
        task.status = "cancelled"
    elif data.get("completed") or data.get("columnId"):
        task.status = _status_for(config, data, task.status)
    if task.status == "done":
        task.completed_at = datetime.now(UTC)
    if "deadline" in data:
        task.deadline = _deadline_from_yougile(data.get("deadline"))
    task.last_status_update_at = datetime.now(UTC)


def _status_for(config: dict[str, Any], data: dict[str, Any], current: str) -> str:
    column_id = str(data.get("columnId") or "")
    columns = config.get("default_column_ids") or {}
    by_column = {str(value): key for key, value in columns.items()}
    if data.get("completed"):
        return "done"
    return by_column.get(column_id, current)


async def _local_assignee(
    session: AsyncSession,
    team_id: UUID,
    data: dict[str, Any],
) -> UUID | None:
    assigned = data.get("assigned") or []
    if not assigned:
        return None
    mapping = await session.scalar(
        select(m.YouGileMappingModel).where(
            m.YouGileMappingModel.team_id == team_id,
            m.YouGileMappingModel.entity_type == "user",
            m.YouGileMappingModel.yougile_id == str(assigned[0]),
        )
    )
    return mapping.local_id if mapping else None


def _deadline_from_yougile(value: Any) -> datetime | None:
    if not isinstance(value, dict) or not value.get("deadline"):
        return None
    return datetime.fromtimestamp(float(value["deadline"]) / 1000, tz=UTC)
