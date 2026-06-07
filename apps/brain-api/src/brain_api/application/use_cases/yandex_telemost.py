"""Yandex Telemost integration use-cases — tenant-scoped, token-encrypted.

Responsibilities:
  - issue/validate one-time OAuth state (CSRF protection, bound to user+team),
  - store access/refresh tokens ONLY encrypted (SecretCipher / Fernet),
  - transparently refresh an expired access token,
  - create a Telemost conference for a team (and for a Telegram chat),
  - never return or log tokens.

The HTTP details live in integrations.yandex_telemost.YandexTelemostClient.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from brain_api.config import Settings
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher
from brain_api.integrations.yandex_telemost import (
    TokenResponse,
    YandexTelemostAuthError,
    YandexTelemostClient,
    YandexTelemostError,
)

logger = logging.getLogger(__name__)

STATE_TTL_MINUTES = 15
# Refresh a bit before actual expiry to avoid racing a 401 mid-request.
_REFRESH_SKEW = timedelta(seconds=60)

DEFAULT_SETTINGS: dict = {
    "enable_meeting_agent_auto_join": False,
    "send_ai_recording_notice_to_chat": True,
    "default_title_template": "Созвон Grey Cardinal — {telegram_chat_title}",
}


class TelemostNotConnected(YandexTelemostError):
    """No connected Telemost integration for this team."""


class TelemostNotConfigured(YandexTelemostError):
    """Server is missing YANDEX_TELEMOST_CLIENT_ID/SECRET."""


# ── Helpers ───────────────────────────────────────────────────────────────────


def _cipher(settings: Settings) -> SecretCipher:
    return SecretCipher(settings.board_creds_encryption_key or "dev-key")


def build_client(settings: Settings) -> YandexTelemostClient:
    if not settings.yandex_telemost_configured:
        raise TelemostNotConfigured("YANDEX_TELEMOST_CLIENT_ID/SECRET are not set")
    return YandexTelemostClient(
        client_id=settings.yandex_telemost_client_id,
        client_secret=settings.yandex_telemost_client_secret,
        redirect_uri=settings.yandex_telemost_redirect_uri,
        scopes=settings.yandex_telemost_scopes,
    )


def effective_settings(integration: m.YandexTelemostIntegrationModel | None) -> dict:
    merged = dict(DEFAULT_SETTINGS)
    if integration is not None and integration.settings:
        merged.update(integration.settings)
    # Recording notice is a safety/consent guarantee — keep it on in MVP.
    merged["send_ai_recording_notice_to_chat"] = True
    return merged


def status_payload(
    integration: m.YandexTelemostIntegrationModel | None, *, configured: bool
) -> dict:
    """API-safe status — never contains tokens."""
    if integration is None or integration.status == "disconnected":
        return {
            "provider": "yandex_telemost",
            "status": "disconnected",
            "connected": False,
            "available": False,
            "server_configured": configured,
            "settings": effective_settings(None),
        }
    return {
        "provider": "yandex_telemost",
        "status": integration.status,
        "connected": integration.status == "connected",
        "available": integration.status == "connected",
        "server_configured": configured,
        "yandex_user_id": integration.yandex_user_id,
        "scopes": integration.scopes,
        "expires_at": integration.expires_at.isoformat() if integration.expires_at else None,
        "connected_at": integration.connected_at.isoformat() if integration.connected_at else None,
        "settings": effective_settings(integration),
    }


# ── Integration CRUD ──────────────────────────────────────────────────────────


async def get_integration(
    session, team_id: UUID
) -> m.YandexTelemostIntegrationModel | None:
    return await session.scalar(
        select(m.YandexTelemostIntegrationModel).where(
            m.YandexTelemostIntegrationModel.team_id == team_id
        )
    )


async def _get_or_create(session, team_id: UUID) -> m.YandexTelemostIntegrationModel:
    integration = await get_integration(session, team_id)
    if integration is None:
        integration = m.YandexTelemostIntegrationModel(
            team_id=team_id, provider="yandex_telemost", status="disconnected"
        )
        session.add(integration)
        await session.flush()
    return integration


async def save_tokens(
    session,
    settings: Settings,
    team_id: UUID,
    token: TokenResponse,
    *,
    yandex_user_id: str | None = None,
) -> m.YandexTelemostIntegrationModel:
    cipher = _cipher(settings)
    integration = await _get_or_create(session, team_id)
    integration.access_token_encrypted = cipher.encrypt_text(token.access_token)
    integration.refresh_token_encrypted = (
        cipher.encrypt_text(token.refresh_token) if token.refresh_token else None
    )
    integration.expires_at = token.expires_at
    integration.scopes = token.scope or settings.yandex_telemost_scopes
    integration.status = "connected"
    integration.connected_at = datetime.now(UTC)
    integration.disconnected_at = None
    if yandex_user_id:
        integration.yandex_user_id = yandex_user_id
    return integration


async def disconnect(session, team_id: UUID) -> m.YandexTelemostIntegrationModel | None:
    integration = await get_integration(session, team_id)
    if integration is None:
        return None
    integration.access_token_encrypted = None
    integration.refresh_token_encrypted = None
    integration.expires_at = None
    integration.status = "disconnected"
    integration.disconnected_at = datetime.now(UTC)
    return integration


async def update_settings(session, team_id: UUID, patch: dict) -> m.YandexTelemostIntegrationModel:
    integration = await _get_or_create(session, team_id)
    merged = dict(integration.settings or {})
    for key in ("enable_meeting_agent_auto_join", "default_title_template"):
        if key in patch:
            merged[key] = patch[key]
    # send_ai_recording_notice_to_chat stays forced-on (see effective_settings).
    integration.settings = merged
    return integration


# ── OAuth state (CSRF) ────────────────────────────────────────────────────────


async def issue_state(session, *, user_id: UUID, team_id: UUID) -> str:
    state = secrets.token_urlsafe(32)
    session.add(
        m.YandexOAuthStateModel(
            state=state,
            user_id=user_id,
            team_id=team_id,
            provider="yandex_telemost",
            expires_at=datetime.now(UTC) + timedelta(minutes=STATE_TTL_MINUTES),
        )
    )
    return state


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


async def consume_state(session, state: str) -> m.YandexOAuthStateModel | None:
    row = await session.scalar(
        select(m.YandexOAuthStateModel).where(m.YandexOAuthStateModel.state == state)
    )
    if row is None or row.used_at is not None:
        return None
    if _as_utc(row.expires_at) < datetime.now(UTC):
        return None
    row.used_at = datetime.now(UTC)
    return row


# ── Token validity / refresh ──────────────────────────────────────────────────


async def ensure_access_token(
    session, settings: Settings, integration: m.YandexTelemostIntegrationModel
) -> str:
    """Return a usable access token, refreshing if needed. Marks the integration
    expired/error on failure and raises TelemostNotConnected."""
    if integration.status != "connected" or not integration.access_token_encrypted:
        raise TelemostNotConnected("Telemost is not connected for this team")

    cipher = _cipher(settings)
    access = cipher.decrypt_text(integration.access_token_encrypted) or ""
    expires_at = integration.expires_at
    needs_refresh = expires_at is not None and _as_utc(expires_at) - _REFRESH_SKEW <= datetime.now(
        UTC
    )
    if not needs_refresh:
        return access

    refresh = (
        cipher.decrypt_text(integration.refresh_token_encrypted)
        if integration.refresh_token_encrypted
        else None
    )
    if not refresh:
        integration.status = "expired"
        raise TelemostNotConnected("Telemost token expired and no refresh token available")

    client = build_client(settings)
    try:
        token = await client.refresh_token(refresh)
    except YandexTelemostAuthError:
        integration.status = "expired"
        raise TelemostNotConnected("Telemost refresh token rejected — reconnect required") from None
    await save_tokens(session, settings, integration.team_id, token)
    return token.access_token


# ── Room creation ─────────────────────────────────────────────────────────────


def _extract_join_url(data: dict) -> str | None:
    return data.get("join_url") or data.get("url") or data.get("joinUrl")


async def create_room_for_team(
    session, settings: Settings, team_id: UUID, *, title: str | None = None
) -> dict:
    integration = await get_integration(session, team_id)
    if integration is None:
        raise TelemostNotConnected("Telemost is not connected for this team")
    access_token = await ensure_access_token(session, settings, integration)
    client = build_client(settings)
    try:
        data = await client.create_conference(access_token, title=title)
    except YandexTelemostAuthError:
        integration.status = "expired"
        raise TelemostNotConnected("Telemost token rejected — reconnect required") from None
    except YandexTelemostError:
        integration.status = "error"
        raise
    join_url = _extract_join_url(data)
    return {
        "join_url": join_url,
        "conference_id": data.get("id"),
        "raw": data,
    }


async def create_room_for_chat(
    session,
    settings: Settings,
    *,
    telegram_chat_id: int,
    created_by_telegram_user_id: int | None = None,
    title: str | None = None,
) -> dict:
    """Resolve team by Telegram chat, create a Telemost room, queue a (stub) join job.

    Returns {ok, join_url, conference_id, settings, team_id} or raises a domain error.
    """
    team = await session.scalar(
        select(m.TeamModel).where(m.TeamModel.tg_chat_id == telegram_chat_id)
    )
    if team is None:
        raise TelemostNotConnected("This Telegram chat is not bound to a team")

    cfg = effective_settings(await get_integration(session, team.id))
    room_title = title or cfg["default_title_template"].format(
        telegram_chat_title=team.name or "команда"
    )
    result = await create_room_for_team(session, settings, team.id, title=room_title)
    join_url = result["join_url"]

    created_by_user_id = None
    if created_by_telegram_user_id is not None:
        created_by_user_id = await session.scalar(
            select(m.UserModel.id).where(
                m.UserModel.telegram_user_id == created_by_telegram_user_id
            )
        )

    # Queue stub — MVP does not auto-join/record. A future worker consumes 'pending'.
    meeting_id = None
    if join_url:
        session.add(
            m.MeetingAgentJoinJobModel(
                team_id=team.id,
                provider="yandex_telemost",
                meeting_url=join_url,
                conference_id=result.get("conference_id"),
                telegram_chat_id=telegram_chat_id,
                created_by_user_id=created_by_user_id,
                created_by_telegram_user_id=created_by_telegram_user_id,
                # auto-join on => 'queued' (a future worker picks it up);
                # off => 'pending' (intent recorded, nothing auto-joins/records).
                status="queued" if cfg["enable_meeting_agent_auto_join"] else "pending",
            )
        )
        # Create a scheduled Meeting so we can run a "who is coming?" RSVP poll
        # in the chat alongside the link.
        meeting = await _create_scheduled_meeting(
            session,
            team_id=team.id,
            title=room_title,
            join_url=join_url,
            created_by_user_id=created_by_user_id,
        )
        meeting_id = meeting.id

    return {
        "ok": True,
        "team_id": team.id,
        "join_url": join_url,
        "conference_id": result.get("conference_id"),
        "meeting_id": meeting_id,
        "settings": cfg,
    }


async def _create_scheduled_meeting(
    session,
    *,
    team_id: UUID,
    title: str,
    join_url: str,
    created_by_user_id: UUID | None,
):
    """Create a minimal scheduled Meeting row for the RSVP poll (independent of UoW)."""
    from sqlalchemy import func

    now = datetime.now(UTC)
    next_seq = (await session.scalar(select(func.max(m.MeetingModel.seq)))) or 0
    next_seq += 1
    meeting = m.MeetingModel(
        seq=next_seq,
        public_id=f"MTG-{next_seq}",
        team_id=team_id,
        title=title,
        status="scheduled",
        state="scheduled",
        scheduled_at=now,
        started_at=now,
        created_by=created_by_user_id,
        created_by_user_id=created_by_user_id,
        external_source="yandex_telemost",
        metadata_json={"join_url": join_url},
    )
    session.add(meeting)
    await session.flush()
    return meeting
