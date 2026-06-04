"""Telemost bot session management endpoints.

Endpoints:
  POST /api/telemost/join                  — create bot session + meeting
  GET  /api/telemost/{bot_session_id}/status — session status
  POST /api/telemost/{bot_session_id}/leave  — stop bot session

On join:
  - validates meeting_url (must be https://)
  - auto-creates meeting_id if not provided
  - creates meeting in shared SimpleStore (source=telemost_bot, status=recording)
  - creates BotSessionData
  - calls worker.start_session() — mock by default, real Playwright hook-ready
  - returns bot_session_id, meeting_id, status

Bot session statuses:
  created → joining → joined → recording → uploading → uploaded → left | error

Worker mode is controlled by TELEMOST_WORKER_MODE env var (default: mock).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brain_api.api.routes.public_api import SimpleStore, get_store
from brain_api.telemost_worker.base import BotSessionData
from brain_api.telemost_worker.factory import get_worker

# ---------------------------------------------------------------------------
# In-memory session registry
# ---------------------------------------------------------------------------

_BOT_SESSIONS: dict[str, BotSessionData] = {}


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Session manager (used by routes + tests)
# ---------------------------------------------------------------------------


class TelemostSessionManager:
    """Manages bot session lifecycle. Thread-safe for single-process demo."""

    @staticmethod
    def create(meeting_url: str, meeting_id: str) -> BotSessionData:
        bot_session_id = "bot_" + uuid.uuid4().hex[:16]
        session = BotSessionData(
            bot_session_id=bot_session_id,
            meeting_id=meeting_id,
            meeting_url=meeting_url,
            status="created",
        )
        _BOT_SESSIONS[bot_session_id] = session
        return session

    @staticmethod
    def get(bot_session_id: str) -> BotSessionData | None:
        return _BOT_SESSIONS.get(bot_session_id)

    @staticmethod
    def leave(bot_session_id: str) -> BotSessionData | None:
        session = _BOT_SESSIONS.get(bot_session_id)
        if session is None:
            return None
        session.status = "left"
        return session

    @staticmethod
    def clear_all() -> None:
        """Used in tests to reset state between cases."""
        _BOT_SESSIONS.clear()


session_manager = TelemostSessionManager()


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


def _validate_meeting_url(url: str) -> None:
    if not url or not url.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="Invalid meeting_url: must start with https://",
        )


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class JoinRequest(BaseModel):
    meeting_url: str
    meeting_id: str = ""


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/telemost", tags=["telemost"])


@router.post("/join")
async def join_meeting(
    body: JoinRequest,
    store: SimpleStore = Depends(get_store),
) -> dict[str, Any]:
    """Create bot session and register meeting in common store.

    The meeting is immediately visible in GET /api/meetings with
    source=telemost_bot and status=recording.
    """
    _validate_meeting_url(body.meeting_url)

    meeting_id = body.meeting_id.strip() or str(uuid.uuid4())

    # Register meeting in shared store so it appears in GET /api/meetings.
    store.ensure_meeting(meeting_id, source="telemost_bot")

    # Create bot session.
    session = session_manager.create(body.meeting_url, meeting_id)

    # Call worker hook (mock by default — no real browser).
    worker = get_worker()
    await worker.start_session(session)

    return {
        "ok": True,
        "meeting_id": meeting_id,
        "bot_session_id": session.bot_session_id,
        "status": session.status,
        "message": "Telemost bot join requested",
    }


@router.get("/{bot_session_id}/status")
async def get_session_status(bot_session_id: str) -> dict[str, Any]:
    session = session_manager.get(bot_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Bot session '{bot_session_id}' not found")
    return {
        "ok": True,
        "bot_session_id": session.bot_session_id,
        "meeting_id": session.meeting_id,
        "status": session.status,
    }


@router.post("/{bot_session_id}/leave")
async def leave_meeting(bot_session_id: str) -> dict[str, Any]:
    session = session_manager.leave(bot_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Bot session '{bot_session_id}' not found")

    worker = get_worker()
    await worker.stop_session(bot_session_id)

    return {
        "ok": True,
        "bot_session_id": session.bot_session_id,
        "meeting_id": session.meeting_id,
        "status": session.status,
        "message": "Telemost bot leave requested",
    }
