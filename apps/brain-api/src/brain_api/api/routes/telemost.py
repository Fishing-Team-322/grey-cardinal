"""Legacy Telemost demo routes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brain_api.api.routes.public_api import SimpleStore, get_store

router = APIRouter(prefix="/api/telemost", tags=["telemost-demo"])


class JoinRequest(BaseModel):
    meeting_url: str
    meeting_id: str | None = None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    def create(self, meeting_url: str, meeting_id: str) -> dict:
        bot_session_id = f"bot_{uuid4().hex}"
        session = {
            "bot_session_id": bot_session_id,
            "meeting_url": meeting_url,
            "meeting_id": meeting_id,
            "status": "joining",
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._sessions[bot_session_id] = session
        return session

    def get(self, bot_session_id: str) -> dict | None:
        return self._sessions.get(bot_session_id)

    def leave(self, bot_session_id: str) -> dict | None:
        session = self.get(bot_session_id)
        if session is not None:
            session["status"] = "left"
        return session

    def clear_all(self) -> None:
        self._sessions.clear()


session_manager = SessionManager()


@router.post("/join")
async def join_telemost(body: JoinRequest, store: SimpleStore = Depends(get_store)) -> dict:
    url = body.meeting_url.strip()
    if not url.startswith("https://telemost.yandex.ru/"):
        raise HTTPException(400, "Invalid Telemost URL")
    meeting_id = body.meeting_id or f"meeting_{uuid4().hex}"
    store.ensure_meeting(meeting_id, source="telemost_bot")
    session = session_manager.create(url, meeting_id)
    return {
        "ok": True,
        "bot_session_id": session["bot_session_id"],
        "meeting_id": meeting_id,
        "status": session["status"],
        "message": "Telemost bot join requested",
    }


@router.get("/{bot_session_id}/status")
async def telemost_status(bot_session_id: str) -> dict:
    session = session_manager.get(bot_session_id)
    if session is None:
        raise HTTPException(404, "Bot session not found")
    return {"ok": True, **session}


@router.post("/{bot_session_id}/leave")
async def leave_telemost(bot_session_id: str) -> dict:
    session = session_manager.leave(bot_session_id)
    if session is None:
        raise HTTPException(404, "Bot session not found")
    return {"ok": True, **session}
