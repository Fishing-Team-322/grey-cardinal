"""Telegram Mini App (WebApp) API — initData-authenticated, tenant-scoped.

The WebApp (static page at /tgapp/) sends Telegram ``initData`` which we verify
with the bot token (HMAC-SHA256 per Telegram spec). No JWT/cabinet login needed.
Returns the signed-in user's tasks and upcoming meetings.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select

from brain_api.api.deps import get_container
from brain_api.application.task_status_service import TaskStatusService
from brain_api.config import get_settings
from brain_api.container import Container
from brain_api.domain.enums import TaskStatus
from brain_api.infrastructure.db import models as m

router = APIRouter(prefix="/api/tgapp", tags=["telegram-mini-app"])

_MAX_AGE_SECONDS = 24 * 3600
_ACTIVE_TASK_STATUSES = ("todo", "in_progress", "blocked")
# Statuses a user may set from the mini app.
_ALLOWED_SET_STATUSES = {"in_progress", "blocked", "done", "todo"}


class OverviewRequest(BaseModel):
    init_data: str


class TaskStatusRequest(BaseModel):
    init_data: str
    status: str


class RsvpRequest(BaseModel):
    init_data: str
    response: str  # yes | no | maybe


async def _auth_user(session, init_data: str) -> m.UserModel:
    settings = get_settings()
    parsed = verify_init_data(init_data, settings.telegram_bot_token)
    if parsed is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid initData")
    try:
        tg_user = json.loads(parsed.get("user", "{}"))
    except json.JSONDecodeError:
        tg_user = {}
    tg_user_id = tg_user.get("id")
    if not tg_user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No user in initData")
    user = await session.scalar(
        select(m.UserModel).where(m.UserModel.telegram_user_id == tg_user_id)
    )
    if user is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Telegram account not linked")
    return user


async def _user_team_ids(session, user_id) -> list:
    rows = await session.execute(
        select(m.TeamMemberModel.team_id).where(m.TeamMemberModel.user_id == user_id)
    )
    return [r[0] for r in rows.all()]


def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """Validate Telegram WebApp initData. Returns parsed fields or None."""
    if not init_data or not bot_token:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True, keep_blank_values=True))
    except ValueError:
        return None
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        return None
    auth_date = int(parsed.get("auth_date", "0") or "0")
    if auth_date and time.time() - auth_date > _MAX_AGE_SECONDS:
        return None
    return parsed


def _deadline_str(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


@router.post("/overview")
async def overview(
    payload: OverviewRequest,
    container: Container = Depends(get_container),
) -> dict:
    settings = get_settings()
    parsed = verify_init_data(payload.init_data, settings.telegram_bot_token)
    if parsed is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid initData")

    try:
        tg_user = json.loads(parsed.get("user", "{}"))
    except json.JSONDecodeError:
        tg_user = {}
    tg_user_id = tg_user.get("id")
    if not tg_user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No user in initData")

    tg_profile = {
        "id": tg_user_id,
        "username": tg_user.get("username"),
        "first_name": tg_user.get("first_name"),
        "last_name": tg_user.get("last_name"),
    }

    async with container.session_factory() as session:
        user = await session.scalar(
            select(m.UserModel).where(m.UserModel.telegram_user_id == tg_user_id)
        )
        if user is None:
            return {
                "linked": False,
                "telegram_user": tg_profile,
                "tasks": [],
                "meetings": [],
            }

        team_rows = await session.execute(
            select(m.TeamMemberModel.team_id, m.TeamModel.name, m.TeamModel.timezone)
            .join(m.TeamModel, m.TeamModel.id == m.TeamMemberModel.team_id)
            .where(m.TeamMemberModel.user_id == user.id)
        )
        teams = team_rows.all()
        team_ids = [row[0] for row in teams]
        tz = teams[0][2] if teams else (user.timezone or "Europe/Moscow")

        # Active tasks: in the user's teams or assigned directly to them.
        task_filter = m.TaskModel.assignee_id == user.id
        if team_ids:
            task_filter = or_(task_filter, m.TaskModel.team_id.in_(team_ids))
        task_rows = await session.execute(
            select(m.TaskModel)
            .where(task_filter, m.TaskModel.status.in_(_ACTIVE_TASK_STATUSES))
            .order_by(m.TaskModel.deadline.is_(None), m.TaskModel.deadline.asc())
            .limit(50)
        )
        tasks = [
            {
                "id": str(t.id),
                "public_id": t.public_id,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "assignee": t.assignee_text,
                "deadline": _deadline_str(t.deadline),
                "mine": t.assignee_id == user.id,
            }
            for t in task_rows.scalars()
        ]

        meetings: list[dict] = []
        if team_ids:
            cutoff = datetime.now(UTC) - timedelta(hours=2)
            mtg_rows = await session.execute(
                select(m.MeetingModel)
                .where(
                    m.MeetingModel.team_id.in_(team_ids),
                    m.MeetingModel.state.in_(("proposed", "scheduled")),
                    or_(
                        m.MeetingModel.scheduled_at.is_(None),
                        m.MeetingModel.scheduled_at >= cutoff,
                    ),
                )
                .order_by(m.MeetingModel.scheduled_at.is_(None), m.MeetingModel.scheduled_at.asc())
                .limit(20)
            )
            for mt in mtg_rows.scalars():
                meta = mt.metadata_json or {}
                meetings.append(
                    {
                        "id": str(mt.id),
                        "public_id": mt.public_id,
                        "title": mt.title or "Созвон",
                        "scheduled_at": _deadline_str(mt.scheduled_at),
                        "state": mt.state,
                        "join_url": meta.get("join_url"),
                    }
                )

        return {
            "linked": True,
            "telegram_user": tg_profile,
            "user": {"display_name": user.display_name, "timezone": tz},
            "teams": [{"id": str(tid), "name": name} for tid, name, _ in teams],
            "tasks": tasks,
            "meetings": meetings,
        }


@router.post("/task/{task_id}/status")
async def set_task_status(
    task_id: str,
    payload: TaskStatusRequest,
    container: Container = Depends(get_container),
) -> dict:
    if payload.status not in _ALLOWED_SET_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported status")
    from uuid import UUID

    try:
        tid = UUID(task_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad task id") from exc

    async with container.session_factory() as session:
        user = await _auth_user(session, payload.init_data)
        team_ids = await _user_team_ids(session, user.id)
        task = await session.get(m.TaskModel, tid)
        if task is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
        if task.assignee_id != user.id and task.team_id not in team_ids:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your task")

    result = await TaskStatusService(container.board_mirror).update_status(
        tid,
        TaskStatus(payload.status),
        actor_id=user.id,
        action="tgapp_status_change",
    )
    return {
        "ok": True,
        "public_id": result.public_id,
        "status": result.status,
        "sync_status": result.sync_status,
    }


@router.post("/meeting/{meeting_id}/rsvp")
async def set_rsvp(
    meeting_id: str,
    payload: RsvpRequest,
    container: Container = Depends(get_container),
) -> dict:
    if payload.response not in {"yes", "no", "maybe"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad response")
    from uuid import UUID

    try:
        mid = UUID(meeting_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad meeting id") from exc

    async with container.session_factory() as session:
        user = await _auth_user(session, payload.init_data)
        meeting = await session.get(m.MeetingModel, mid)
        if meeting is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found")
        rsvp = await session.scalar(
            select(m.MeetingRsvpModel).where(
                m.MeetingRsvpModel.meeting_id == mid,
                m.MeetingRsvpModel.user_id == user.id,
            )
        )
        if rsvp is None:
            session.add(
                m.MeetingRsvpModel(
                    meeting_id=mid, user_id=user.id, status=payload.response
                )
            )
        else:
            rsvp.status = payload.response
        await session.commit()
    return {"ok": True, "response": payload.response}
