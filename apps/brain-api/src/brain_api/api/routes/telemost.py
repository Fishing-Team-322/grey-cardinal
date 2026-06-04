"""Telemost bot session management.

Endpoints:
  POST /api/telemost/join
  GET  /api/telemost/{bot_session_id}/status
  POST /api/telemost/{bot_session_id}/leave

Demo/mock implementation: manages bot session state in memory.
Real Telemost joiner can be plugged into TelemostSessionManager.join() later.

Bot session statuses:
  created → joining → joined → recording → uploading → uploaded → left | error
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Session manager
# ---------------------------------------------------------------------------

_BOT_SESSIONS: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class TelemostSessionManager:
    """In-memory store for bot sessions. Thread-safe for single-process demo."""

    @staticmethod
    def create(meeting_url: str, meeting_id: str) -> dict[str, Any]:
        bot_session_id = "bot_" + uuid.uuid4().hex[:16]
        session: dict[str, Any] = {
            "bot_session_id": bot_session_id,
            "meeting_id": meeting_id,
            "meeting_url": meeting_url,
            "status": "joining",
            "created_at": _now_iso(),
        }
        _BOT_SESSIONS[bot_session_id] = session
        # Hook point: spawn real Telemost joiner here when available.
        return session

    @staticmethod
    def get(bot_session_id: str) -> dict[str, Any] | None:
        return _BOT_SESSIONS.get(bot_session_id)

    @staticmethod
    def leave(bot_session_id: str) -> dict[str, Any] | None:
        session = _BOT_SESSIONS.get(bot_session_id)
        if session is None:
            return None
        session["status"] = "left"
        return session

    @staticmethod
    def clear_all() -> None:
        """Used in tests to reset state."""
        _BOT_SESSIONS.clear()


# Singleton — overridable in tests via module-level replacement.
session_manager = TelemostSessionManager()


def _validate_meeting_url(url: str) -> None:
    if not url or not url.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="Invalid meeting_url: must be a valid https:// Telemost URL",
        )


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class JoinRequest(BaseModel):
    meeting_url: str
    meeting_id: str = ""


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/telemost", tags=["telemost"])


@router.post("/join")
async def join_meeting(body: JoinRequest) -> dict[str, Any]:
    _validate_meeting_url(body.meeting_url)

    meeting_id = body.meeting_id.strip() or str(uuid.uuid4())
    session = session_manager.create(body.meeting_url, meeting_id)

    return {
        "ok": True,
        "meeting_id": meeting_id,
        "bot_session_id": session["bot_session_id"],
        "status": session["status"],
        "message": "Telemost bot join requested",
    }


@router.get("/{bot_session_id}/status")
async def get_session_status(bot_session_id: str) -> dict[str, Any]:
    session = session_manager.get(bot_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Bot session '{bot_session_id}' not found")
    return {
        "ok": True,
        "bot_session_id": session["bot_session_id"],
        "meeting_id": session["meeting_id"],
        "status": session["status"],
    }


@router.post("/{bot_session_id}/leave")
async def leave_meeting(bot_session_id: str) -> dict[str, Any]:
    session = session_manager.leave(bot_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Bot session '{bot_session_id}' not found")
    return {
        "ok": True,
        "bot_session_id": session["bot_session_id"],
        "meeting_id": session["meeting_id"],
        "status": session["status"],
        "message": "Telemost bot leave requested",
    }
