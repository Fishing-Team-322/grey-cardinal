"""Public session endpoint — for tray agent and dashboard widgets.

GET /api/session/current  — no auth required, returns active meeting status.
Tray agent polls this every 5s to know whether to start/stop recording.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from brain_api.api.deps import get_container
from brain_api.application.use_cases.manage_meetings import meeting_response
from brain_api.container import Container

router = APIRouter(prefix="/api", tags=["session"])


@router.get("/session/current")
async def session_current(
    container: Container = Depends(get_container),
) -> dict:
    """Return the active workspace meeting, if any.

    Used by the desktop tray agent to decide whether to start recording.
    No authentication required — meeting IDs are not sensitive.
    """
    async with container.make_uow() as uow:
        meeting = await uow.meetings.get_active_for_chat(None)
        if meeting is None:
            return {"active": False, "meeting_id": None, "transcript_count": 0}
        dto = await meeting_response(uow, meeting)
        return {
            "active": True,
            "meeting_id": meeting.public_id,
            "status": (
                meeting.status.value
                if hasattr(meeting.status, "value")
                else str(meeting.status)
            ),
            "transcript_count": dto.transcript_count,
            "proposal_count": dto.proposal_count,
            "started_at": meeting.started_at.isoformat() if meeting.started_at else None,
        }
