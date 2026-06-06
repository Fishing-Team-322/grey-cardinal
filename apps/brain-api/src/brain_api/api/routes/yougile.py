"""YouGile integration endpoints — login/connect onboarding, status, disconnect.

The user never types an API key: they enter their YouGile email+password, pick a
company, and we fetch-or-create the API key server-side, encrypt it with
SecretCipher and store it on the team. The password lives only in RAM (encrypted)
inside a short-lived onboarding token (in-process TTL store — single pod; swap for
Redis when scaling).
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.deps import get_container
from brain_api.api.rbac import build_tenant_context, require_team_member, require_team_role
from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.application.use_cases.yougile_discovery import discover_yougile_workspace
from brain_api.config import Settings, get_settings
from brain_api.container import Container
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher
from brain_api.integrations.yougile import YouGileAuthError, YouGileClient, YouGileError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/teams/{team_id}/integrations/yougile", tags=["yougile"])

WEBHOOK_EVENTS = ("task-created", "task-updated", "task-deleted", "task-moved")


# ── In-process onboarding token store (password encrypted, TTL) ───────────────
@dataclass
class _Onboarding:
    login: str
    password_enc: bytes
    companies: list[dict[str, Any]]
    expires_at: float


_ONBOARDING: dict[str, _Onboarding] = {}


def _purge_expired() -> None:
    now = time.monotonic()
    for tok in [t for t, v in _ONBOARDING.items() if v.expires_at < now]:
        _ONBOARDING.pop(tok, None)


def _cipher(settings: Settings) -> SecretCipher:
    return SecretCipher(settings.board_creds_encryption_key or "dev-key")


def _public_base(settings: Settings) -> str:
    return (settings.public_base_url or settings.telegram_public_base_url or "").rstrip("/")


async def _require_manager(team_id: UUID, user_id: UUID, session: AsyncSession) -> m.TeamModel:
    ctx = await build_tenant_context(user_id, session)
    require_team_role(ctx, team_id, "manager")
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    return team


# ── Schemas ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    login: str
    password: str


class ConnectRequest(BaseModel):
    onboarding_token: str
    company_id: str


class PrimaryProjectRequest(BaseModel):
    project_id: str


# ── POST /login ───────────────────────────────────────────────────────────────
@router.post("/login")
async def yougile_login(
    team_id: UUID,
    body: LoginRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    await _require_manager(team_id, current_user.id, session)
    client = YouGileClient("", base_url=settings.yougile_api_base_url)
    try:
        companies = await client.auth_companies(body.login, body.password)
    except YouGileAuthError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"error": "invalid_credentials"},
        ) from None
    except YouGileError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"YouGile unavailable: {exc}") from exc

    _purge_expired()
    token = secrets.token_urlsafe(24)
    slim = [{"id": str(c["id"]), "name": c.get("name", "")} for c in companies]
    _ONBOARDING[token] = _Onboarding(
        login=body.login,
        password_enc=_cipher(settings).encrypt_text(body.password),
        companies=slim,
        expires_at=time.monotonic() + settings.yougile_onboarding_token_ttl_seconds,
    )
    return {"companies": slim, "onboarding_token": token}


# ── POST /connect ───────────────────────────────────────────────────────────────
@router.post("/connect")
async def yougile_connect(
    team_id: UUID,
    body: ConnectRequest,
    current_user: CurrentUser,
    background: BackgroundTasks,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    team = await _require_manager(team_id, current_user.id, session)

    _purge_expired()
    onboarding = _ONBOARDING.pop(body.onboarding_token, None)
    if onboarding is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"error": "expired_onboarding"})
    cipher = _cipher(settings)
    password = cipher.decrypt_text(onboarding.password_enc) or ""
    company = next((c for c in onboarding.companies if c["id"] == body.company_id), None)
    if company is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"error": "unknown_company"})

    client = YouGileClient("", base_url=settings.yougile_api_base_url)
    try:
        keys = await client.auth_keys_get(onboarding.login, password, body.company_id)
        api_key = (
            keys[0]["key"]
            if keys
            else await client.auth_keys_create(onboarding.login, password, body.company_id)
        )
    except YouGileAuthError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"error": "invalid_credentials"},
        ) from None
    except YouGileError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"YouGile unavailable: {exc}") from exc

    webhook_secret = secrets.token_urlsafe(24)
    team.board_provider = "yougile"
    team.board_credentials_encrypted = cipher.encrypt_text(json.dumps({"api_key": api_key}))
    config = dict(team.board_config or {})
    config.update(
        {
            "yougile_company_id": body.company_id,
            "yougile_company_name": company["name"],
            "synced_at": None,
            "webhook_secret": webhook_secret,
            "integration_status": "connected",
        }
    )

    # Subscribe to webhooks (best-effort — connect must not fail if this does).
    base = _public_base(settings)
    if base:
        config["webhook_subscriptions"] = await _subscribe_webhooks(
            api_key, settings.yougile_api_base_url, base, team_id, webhook_secret
        )
    team.board_config = config
    session.add(team)
    await session.commit()

    background.add_task(
        discover_yougile_workspace,
        container.session_factory,
        team_id=team_id,
        api_base_url=settings.yougile_api_base_url,
        cipher=cipher,
    )
    return {
        "connected": True,
        "company": {"id": body.company_id, "name": company["name"]},
        "sync_status": "in_progress",
    }


async def _subscribe_webhooks(
    api_key: str, api_base: str, public_base: str, team_id: UUID, secret: str
) -> list[dict]:
    client = YouGileClient(api_key, base_url=api_base)
    root_url = f"{public_base}/api/integrations/yougile/webhook/{team_id}"
    try:
        existing = await client.list_webhooks()
    except YouGileError:
        existing = []
    subs: list[dict] = []
    for event in WEBHOOK_EVENTS:
        url = f"{root_url}?secret={secret}&event={event}"
        current = next(
            (
                webhook
                for webhook in existing
                if webhook.get("url") == url
                and webhook.get("event") == event
                and not webhook.get("disabled")
                and not webhook.get("deleted")
            ),
            None,
        )
        if current is not None:
            subs.append({"event": event, "id": current.get("id")})
            continue
        try:
            wh = await client.create_webhook(url, event)
            subs.append({"event": event, "id": wh.get("id")})
        except YouGileError as exc:
            logger.warning("YouGile webhook subscribe failed for %s: %s", event, exc)
    return subs


# ── GET /status ───────────────────────────────────────────────────────────────
@router.get("/status")
async def yougile_status(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    ctx = await build_tenant_context(current_user.id, session)
    require_team_member(ctx, team_id)
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    config = dict(team.board_config or {})
    connected = bool(team.board_provider == "yougile" and team.board_credentials_encrypted)
    if not connected:
        integration_status = config.get("integration_status")
        return {
            "connected": False,
            "error": integration_status if integration_status == "auth_error" else None,
            "reconnect_required": integration_status == "auth_error",
        }

    stats = {}
    for entity in ("project", "board", "column", "task"):
        stats[entity + "s"] = await session.scalar(
            select(func.count())
            .select_from(m.YouGileMappingModel)
            .where(
                m.YouGileMappingModel.team_id == team_id,
                m.YouGileMappingModel.entity_type == entity,
            )
        )
    primary = None
    if config.get("yougile_project_id"):
        primary = {"id": config["yougile_project_id"], "name": config.get("yougile_project_name")}
    remaining = None
    try:
        api_key = json.loads(
            _cipher(settings).decrypt_text(team.board_credentials_encrypted) or "{}"
        ).get("api_key", "")
        remaining = YouGileClient(
            api_key, base_url=settings.yougile_api_base_url
        ).rate_limit_remaining
    except Exception:  # noqa: BLE001 — status must not fail on rate-limit probe
        pass
    return {
        "connected": True,
        "company": {
            "id": config.get("yougile_company_id"),
            "name": config.get("yougile_company_name"),
        },
        "last_synced_at": config.get("synced_at"),
        "primary_project": primary,
        "stats": stats,
        "rate_limit_remaining": remaining,
    }


# ── DELETE (disconnect) ─────────────────────────────────────────────────────────
@router.put("/primary-project")
async def set_primary_project(
    team_id: UUID,
    body: PrimaryProjectRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    team = await _require_manager(team_id, current_user.id, session)
    project = await session.scalar(
        select(m.YouGileMappingModel).where(
            m.YouGileMappingModel.team_id == team_id,
            m.YouGileMappingModel.entity_type == "project",
            m.YouGileMappingModel.yougile_id == body.project_id,
        )
    )
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "YouGile project not found")

    boards = (
        (
            await session.execute(
                select(m.YouGileMappingModel).where(
                    m.YouGileMappingModel.team_id == team_id,
                    m.YouGileMappingModel.entity_type == "board",
                ).order_by(
                    m.YouGileMappingModel.last_synced_at,
                    m.YouGileMappingModel.id,
                )
            )
        )
        .scalars()
        .all()
    )
    primary_boards = [
        row for row in boards if str((row.payload or {}).get("projectId") or "") == body.project_id
    ]
    config = dict(team.board_config or {})
    config["yougile_project_id"] = body.project_id
    config["yougile_project_name"] = (project.payload or {}).get("title") or (
        project.payload or {}
    ).get("name")
    config["default_board_id"] = primary_boards[0].yougile_id if primary_boards else None
    config["default_column_ids"] = await _default_columns_for_board(
        session,
        team_id,
        config["default_board_id"],
    )
    team.board_config = config
    session.add(team)
    await session.commit()
    return {
        "primary_project": {
            "id": body.project_id,
            "name": config["yougile_project_name"],
        },
        "default_board_id": config["default_board_id"],
        "default_column_ids": config["default_column_ids"],
    }


async def _default_columns_for_board(
    session: AsyncSession,
    team_id: UUID,
    board_id: str | None,
) -> dict[str, str]:
    if not board_id:
        return {}
    columns = (
        (
            await session.execute(
                select(m.YouGileMappingModel).where(
                    m.YouGileMappingModel.team_id == team_id,
                    m.YouGileMappingModel.entity_type == "column",
                ).order_by(
                    m.YouGileMappingModel.last_synced_at,
                    m.YouGileMappingModel.id,
                )
            )
        )
        .scalars()
        .all()
    )
    columns = [row for row in columns if str((row.payload or {}).get("boardId") or "") == board_id]
    aliases = {
        "todo": {"к выполнению", "todo", "to do", "backlog"},
        "in_progress": {"в работе", "in progress", "doing"},
        "done": {"готово", "done", "completed"},
    }
    result: dict[str, str] = {}
    for row in columns:
        title = str((row.payload or {}).get("title") or "").strip().lower()
        for status_key, names in aliases.items():
            if title in names:
                result[status_key] = row.yougile_id
    if len(result) < 3 and len(columns) >= 3:
        for status_key, row in zip(("todo", "in_progress", "done"), columns, strict=False):
            result.setdefault(status_key, row.yougile_id)
    return result


@router.delete("", status_code=status.HTTP_200_OK)
async def yougile_disconnect(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    team = await _require_manager(team_id, current_user.id, session)
    config = dict(team.board_config or {})

    # Best-effort unsubscribe (PUT disabled — YouGile has no DELETE /webhooks/{id}).
    subs = config.get("webhook_subscriptions") or []
    if subs and team.board_credentials_encrypted:
        try:
            api_key = json.loads(
                _cipher(settings).decrypt_text(team.board_credentials_encrypted) or "{}"
            ).get("api_key", "")
            client = YouGileClient(api_key, base_url=settings.yougile_api_base_url)
            for sub in subs:
                if sub.get("id"):
                    await client.disable_webhook(sub["id"])
        except YouGileError as exc:
            logger.warning("YouGile webhook unsubscribe failed: %s", exc)

    team.board_provider = "mock"
    team.board_credentials_encrypted = None
    team.board_config = {
        k: v
        for k, v in config.items()
        if not k.startswith("yougile_")
        and k
        not in {
            "webhook_secret",
            "webhook_subscriptions",
            "default_board_id",
            "default_column_ids",
            "synced_at",
        }
    }
    session.add(team)
    await session.commit()
    return {"connected": False}
