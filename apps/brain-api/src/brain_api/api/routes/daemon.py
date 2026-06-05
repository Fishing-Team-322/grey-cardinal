"""Daemon (desktop-agent) state endpoint — production, tenant-scoped.

Заменяет небезопасный `/api/session/current` (без auth, глобальный single-tenant)
для основного поллинга демона. Демон спрашивает «можно ли сейчас записывать?»:

    GET /api/daemon/state
    X-Agent-Token: <client_session_id, выданный при register_device>

Ответ привязан к встречам команд, в которых состоит пользователь демона. Демон
включается только в окне созвона:

    idle      — встреч нет / ещё рано / уже поздно
    armed     — за MEETING_ARM_MINUTES_BEFORE минут до начала (пора готовиться)
    recording — идёт время созвона (scheduled_at .. scheduled_at+duration)

Состояние считается из времени встречи, поэтому работает даже без отдельного
scheduler'а, который персистит переходы (см. будущий meeting state-machine).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from brain_api.api.deps import get_container
from brain_api.config import get_settings
from brain_api.container import Container
from brain_api.infrastructure.db import models as m

router = APIRouter(prefix="/api/daemon", tags=["daemon"])

_ACTIVE_MEETING_STATES = ("scheduled", "armed", "recording")
_DEAD_SESSION_STATUSES = ("revoked", "expired")


class DaemonAuthError(Exception):
    """Невалидный/просроченный agent-token."""


def _extract_token(x_agent_token: str | None, authorization: str | None) -> str | None:
    if x_agent_token:
        return x_agent_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


@router.get("/state")
async def daemon_state(
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    authorization: str | None = Header(default=None),
    container: Container = Depends(get_container),
) -> dict:
    token = _extract_token(x_agent_token, authorization)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing agent token")
    settings = get_settings()
    now = datetime.now(UTC)
    async with container.session_factory() as session:
        try:
            return await resolve_daemon_state(session, token, now, settings)
        except DaemonAuthError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid agent token") from exc


async def resolve_daemon_state(session, token: str, now: datetime, settings) -> dict:
    client_session = await _resolve_session(session, token)
    if client_session is None:
        raise DaemonAuthError()
    team_ids = await _user_team_ids(session, client_session.user_id)
    meeting = await _pick_meeting(session, team_ids, now, settings) if team_ids else None
    state, recording_started_at = _compute_state(meeting, now, settings)
    return _payload(state, meeting, recording_started_at, now, settings)


async def _resolve_session(session, token: str):
    try:
        session_id = UUID(token)
    except (ValueError, AttributeError):
        return None
    cs = await session.get(m.ClientSessionModel, session_id)
    if cs is None or cs.status in _DEAD_SESSION_STATUSES:
        return None
    return cs


async def _user_team_ids(session, user_id: UUID) -> list[UUID]:
    rows = await session.execute(
        select(m.TeamMemberModel.team_id).where(m.TeamMemberModel.user_id == user_id)
    )
    return [r[0] for r in rows.all()]


async def _pick_meeting(session, team_ids: list[UUID], now: datetime, settings):
    """Ближайшая релевантная встреча команд пользователя (окно arm..end)."""
    default_duration = settings.meeting_default_duration_minutes
    window_start = now - timedelta(minutes=default_duration)
    window_end = now + timedelta(minutes=settings.meeting_arm_minutes_before)
    rows = await session.execute(
        select(m.MeetingModel)
        .where(
            m.MeetingModel.team_id.in_(team_ids),
            m.MeetingModel.state.in_(_ACTIVE_MEETING_STATES),
            m.MeetingModel.scheduled_at.is_not(None),
            m.MeetingModel.scheduled_at >= window_start,
            m.MeetingModel.scheduled_at <= window_end,
        )
        .order_by(m.MeetingModel.scheduled_at)
    )
    return rows.scalars().first()


def _compute_state(meeting, now: datetime, settings) -> tuple[str, datetime | None]:
    if meeting is None or meeting.scheduled_at is None:
        return "idle", None
    scheduled_at = _as_utc(meeting.scheduled_at)
    duration = meeting.duration_minutes or settings.meeting_default_duration_minutes
    arm_at = scheduled_at - timedelta(minutes=settings.meeting_arm_minutes_before)
    end_at = scheduled_at + timedelta(minutes=duration)
    if now < arm_at:
        return "idle", None
    if now < scheduled_at:
        return "armed", None
    if now < end_at:
        return "recording", scheduled_at
    return "idle", None


def _payload(state, meeting, recording_started_at, now: datetime, settings) -> dict:
    return {
        "state": state,
        "meeting_id": str(meeting.id) if meeting else None,
        "meeting_public_id": meeting.public_id if meeting else None,
        "team_id": str(meeting.team_id) if meeting and meeting.team_id else None,
        "scheduled_at": _as_utc(meeting.scheduled_at).isoformat()
        if meeting and meeting.scheduled_at
        else None,
        "recording_started_at": recording_started_at.isoformat()
        if recording_started_at
        else None,
        "max_duration_minutes": (
            meeting.duration_minutes if meeting and meeting.duration_minutes
            else settings.meeting_default_duration_minutes
        ),
        "server_time": now.isoformat(),
    }


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
