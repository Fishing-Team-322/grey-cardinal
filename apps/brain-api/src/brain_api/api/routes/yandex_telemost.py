"""Yandex Telemost OAuth + room endpoints (tenant-scoped).

Flow: cabinet → connect/start (issue CSRF state, return Yandex authorize URL) →
user authorizes → Yandex redirects to /oauth/callback → exchange code → store
encrypted tokens → cabinet shows connected.

Tokens are never serialized to responses. ClientSecret comes only from env
(Settings); it is never logged or echoed.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.rbac import build_tenant_context, require_team_member, require_team_role
from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.application.use_cases import yandex_telemost as svc
from brain_api.config import Settings, get_settings
from brain_api.infrastructure.db import models as m
from brain_api.integrations.yandex_telemost import YandexTelemostError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations/yandex-telemost", tags=["yandex-telemost"])


# ── Team resolution ───────────────────────────────────────────────────────────


async def _resolve_team(
    current_user, session: AsyncSession, team_id: UUID | None, *, role: str | None
) -> UUID:
    ctx = await build_tenant_context(current_user.id, session)
    if team_id is None:
        # Pick the user's team — prefer one where they are manager.
        manager_teams = [tid for tid, r in ctx.team_roles.items() if r == "manager"]
        candidates = manager_teams or list(ctx.team_roles.keys())
        if not candidates:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No team for current user")
        team_id = candidates[0]
    if role is None:
        require_team_member(ctx, team_id)
    else:
        require_team_role(ctx, team_id, role)
    return team_id


def _frontend_redirect(settings: Settings, query: str) -> str:
    base = (
        settings.public_base_url
        or settings.telegram_public_base_url
        or "https://fishingteam.su"
    ).rstrip("/")
    return f"{base}/app/integrations/telemost?{query}"


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("/status")
async def telemost_status(
    current_user: CurrentUser,
    team_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    tid = await _resolve_team(current_user, session, team_id, role=None)
    integration = await svc.get_integration(session, tid)
    return svc.status_payload(integration, configured=settings.yandex_telemost_configured)


# ── Connect (start OAuth) ─────────────────────────────────────────────────────


class ConnectStartRequest(BaseModel):
    team_id: UUID | None = None


@router.post("/connect/start")
async def connect_start(
    body: ConnectStartRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.yandex_telemost_configured:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Yandex Telemost is not configured on the server (missing client id/secret)",
        )
    tid = await _resolve_team(current_user, session, body.team_id, role="manager")
    state = await svc.issue_state(session, user_id=current_user.id, team_id=tid)
    client = svc.build_client(settings)
    url = client.build_authorization_url(state)
    await session.commit()
    return {"authorization_url": url}


# ── OAuth callback (Yandex → us) ──────────────────────────────────────────────


@router.get("/oauth/callback")
async def oauth_callback(
    session: AsyncSession = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    settings = get_settings()
    if error:
        logger.warning("[telemost] oauth callback error=%s", error)
        return RedirectResponse(_frontend_redirect(settings, "error=denied"), status_code=302)
    if not code or not state:
        return RedirectResponse(_frontend_redirect(settings, "error=invalid"), status_code=302)

    state_row = await svc.consume_state(session, state)
    if state_row is None:
        await session.commit()
        return RedirectResponse(_frontend_redirect(settings, "error=state"), status_code=302)

    client = svc.build_client(settings)
    try:
        token = await client.exchange_code_for_token(code)
    except YandexTelemostError as exc:
        logger.warning("[telemost] token exchange failed: %s", type(exc).__name__)
        await session.commit()
        return RedirectResponse(_frontend_redirect(settings, "error=exchange"), status_code=302)

    await svc.save_tokens(session, settings, state_row.team_id, token)
    await session.commit()
    return RedirectResponse(_frontend_redirect(settings, "connected=1"), status_code=302)


# ── Disconnect ────────────────────────────────────────────────────────────────


class TeamBody(BaseModel):
    team_id: UUID | None = None


def _recording_job_payload(job: m.MeetingAgentJoinJobModel) -> dict:
    return {
        "id": str(job.id),
        "meeting_id": str(job.meeting_id) if job.meeting_id else None,
        "meeting_url": job.meeting_url,
        "conference_id": job.conference_id,
        "status": job.status,
        "error_message": job.error_message,
        "attempts": job.attempts,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(),
    }


@router.post("/disconnect")
async def disconnect(
    body: TeamBody,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = await _resolve_team(current_user, session, body.team_id, role="manager")
    await svc.disconnect(session, tid)
    await session.commit()
    return {"ok": True, "status": "disconnected"}


# ── Recording agent jobs ──────────────────────────────────────────────────────


@router.get("/recording-jobs")
async def recording_jobs(
    current_user: CurrentUser,
    team_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> dict:
    tid = await _resolve_team(current_user, session, team_id, role=None)
    rows = (
        await session.execute(
            select(m.MeetingAgentJoinJobModel)
            .where(
                m.MeetingAgentJoinJobModel.team_id == tid,
                m.MeetingAgentJoinJobModel.provider == "yandex_telemost",
            )
            .order_by(m.MeetingAgentJoinJobModel.created_at.desc())
            .limit(20)
        )
    ).scalars()
    return {"items": [_recording_job_payload(row) for row in rows]}


@router.post("/recording-jobs/{job_id}/start")
async def start_recording_job(
    job_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    job = await session.get(m.MeetingAgentJoinJobModel, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording job not found")
    await _resolve_team(current_user, session, job.team_id, role="manager")
    if job.status not in {"pending", "failed"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Recording job cannot be started")
    job.status = "queued"
    job.error_message = None
    job.worker_id = None
    await session.commit()
    return _recording_job_payload(job)


@router.post("/recording-jobs/{job_id}/stop")
async def stop_recording_job(
    job_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    job = await session.get(m.MeetingAgentJoinJobModel, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording job not found")
    await _resolve_team(current_user, session, job.team_id, role="manager")
    if job.status in {"joining", "recording"}:
        job.status = "stop_requested"
    elif job.status in {"pending", "queued"}:
        job.status = "completed"
    await session.commit()
    return _recording_job_payload(job)


# ── Settings ──────────────────────────────────────────────────────────────────


class SettingsBody(BaseModel):
    team_id: UUID | None = None
    enable_meeting_agent_auto_join: bool | None = None
    default_title_template: str | None = None


@router.patch("/settings")
async def update_settings(
    body: SettingsBody,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    tid = await _resolve_team(current_user, session, body.team_id, role="manager")
    patch = body.model_dump(exclude_none=True, exclude={"team_id"})
    integration = await svc.update_settings(session, tid, patch)
    await session.commit()
    return svc.status_payload(integration, configured=settings.yandex_telemost_configured)


# ── Test create room ──────────────────────────────────────────────────────────


@router.post("/test-create-room")
async def test_create_room(
    body: TeamBody,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    tid = await _resolve_team(current_user, session, body.team_id, role="manager")
    try:
        result = await svc.create_room_for_team(
            session, settings, tid, title="Grey Cardinal — тест"
        )
    except svc.TelemostNotConnected as exc:
        await session.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except YandexTelemostError as exc:
        await session.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Telemost API error") from exc
    await session.commit()
    return {"ok": True, "join_url": result["join_url"], "conference_id": result["conference_id"]}
