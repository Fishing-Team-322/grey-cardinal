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
from brain_api.config import get_settings
from brain_api.container import Container
from brain_api.infrastructure.db import models as m

router = APIRouter(prefix="/api/tgapp", tags=["telegram-mini-app"])

_MAX_AGE_SECONDS = 24 * 3600
_ACTIVE_TASK_STATUSES = ("todo", "in_progress", "blocked")


class OverviewRequest(BaseModel):
    init_data: str


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
