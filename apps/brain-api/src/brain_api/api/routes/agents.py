"""Desktop / tray agent pairing + lifecycle — DB-backed, tenant-scoped.

Replaces the old demo AgentsStore (JSON file, single global "workspace"). Pairing
now binds a real DeviceModel + ClientSession to the authenticated user, and the
token returned by /register is a ClientSession id — the *same* token consumed by
/api/daemon/state and /api/daemon/v2/uploads (see daemon.py). There is no parallel
agent-auth model: an agent obtained via a pairing code and one obtained via
/api/daemon/token are indistinguishable downstream.

  POST /api/agents/pairing-code        (JWT)            — issue one-time pairing code
  POST /api/agents/register            (pairing code)   — exchange code for a token
  GET  /api/agents                     (JWT)            — list the user's agents
  POST /api/agents/heartbeat           (X-Agent-Token)  — liveness ping
  POST /api/agents/{device_id}/unpair  (JWT)            — revoke an agent

Audio uploaded by an agent goes through /api/daemon/v2/uploads, which runs the
real semantic parser and creates a team task proposal for the user's team.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.api.routes.daemon import _extract_token, _resolve_session
from brain_api.infrastructure.db import models as m

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["agents"])

PAIRING_TTL_MINUTES = 15
ONLINE_WINDOW_SECONDS = 90
_CODE_ALPHABET = "0123456789"


def _gen_pairing_code() -> str:
    return "GC-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _agent_view(device: m.DeviceModel, now: datetime) -> dict:
    last_seen = device.last_seen_at
    online = (
        last_seen is not None
        and (now - _as_utc(last_seen)).total_seconds() <= ONLINE_WINDOW_SECONDS
    )
    return {
        "agent_id": str(device.id),
        "device_name": device.device_name,
        "platform": device.platform,
        "version": device.app_version,
        "online": online,
        "last_seen_at": _as_utc(last_seen).isoformat() if last_seen else None,
        "created_at": _as_utc(device.created_at).isoformat() if device.created_at else None,
    }


# ── Pairing code (issued in the user cabinet) ─────────────────────────────────

@router.post("/agents/pairing-code")
async def create_pairing_code(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    code = _gen_pairing_code()
    expires_at = now + timedelta(minutes=PAIRING_TTL_MINUTES)
    session.add(
        m.DeviceLinkCodeModel(user_id=current_user.id, code=code, expires_at=expires_at)
    )
    await session.commit()
    return {
        "pairing_code": code,
        "expires_at": expires_at.isoformat(),
        "expires_in_minutes": PAIRING_TTL_MINUTES,
    }


# ── Register (agent exchanges code for a token) ───────────────────────────────

class RegisterAgentRequest(BaseModel):
    pairing_code: str
    device_name: str = ""
    platform: str = "windows"
    daemon_version: str = ""


@router.post("/agents/register")
async def register_agent(
    body: RegisterAgentRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    link = await session.scalar(
        select(m.DeviceLinkCodeModel).where(m.DeviceLinkCodeModel.code == body.pairing_code.strip())
    )
    if link is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid pairing code")
    if link.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "pairing code already used")
    if _as_utc(link.expires_at) < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "pairing code expired")

    link.used_at = now
    device = m.DeviceModel(
        user_id=link.user_id,
        device_name=body.device_name or "PC Agent",
        platform=body.platform or "windows",
        app_version=body.daemon_version or None,
        last_seen_at=now,
    )
    session.add(device)
    await session.flush()
    client_session = m.ClientSessionModel(
        user_id=link.user_id, device_id=device.id, status="active", started_at=now
    )
    session.add(client_session)
    await session.commit()
    return {
        "agent_id": str(device.id),
        "agent_token": str(client_session.id),
        "user_id": str(link.user_id),
    }


# ── Listing / heartbeat / unpair ──────────────────────────────────────────────

@router.get("/agents")
async def list_agents(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(UTC)
    rows = await session.execute(
        select(m.DeviceModel)
        .where(m.DeviceModel.user_id == current_user.id)
        .order_by(m.DeviceModel.created_at.desc())
    )
    return {"agents": [_agent_view(d, now) for d in rows.scalars().all()]}


class HeartbeatRequest(BaseModel):
    status: str = "idle"
    version: str | None = None
    device_name: str | None = None


@router.post("/agents/heartbeat")
async def heartbeat(
    body: HeartbeatRequest,
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> dict:
    token = _extract_token(x_agent_token, authorization)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing agent token")
    cs = await _resolve_session(session, token)
    if cs is None or cs.device_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid agent token")
    now = datetime.now(UTC)
    device = await session.get(m.DeviceModel, cs.device_id)
    if device is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid agent token")
    device.last_seen_at = now
    cs.last_seen_at = now
    if body.version:
        device.app_version = body.version
    if body.device_name:
        device.device_name = body.device_name
    await session.commit()
    return {"agent": _agent_view(device, now)}


@router.post("/agents/{device_id}/unpair")
async def unpair_agent(
    device_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    device = await session.get(m.DeviceModel, device_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    # Revoke any live tokens for this device, then drop the device.
    await session.execute(
        update(m.ClientSessionModel)
        .where(m.ClientSessionModel.device_id == device_id)
        .values(status="revoked", device_id=None)
    )
    await session.delete(device)
    await session.commit()
    return {"agent_id": str(device_id), "unpaired": True}
