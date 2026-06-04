"""Demo brain pipeline routes (autonomous, no DB).

Endpoints:
  POST /api/chat/messages                      — ingest message → proposal
  GET  /api/task-proposals                     — list proposals
  POST /api/task-proposals/{id}/confirm        — confirm → create task on board
  POST /api/task-proposals/{id}/reject         — reject → no task
  GET  /api/tasks                              — list tasks
  GET  /api/board                              — board columns (todo/in_progress/done)
  POST /api/tasks/{id}/move                    — move task between statuses
  GET  /api/digest/evening                     — evening digest from real data
  GET  /api/meetings/{id}/transcript           — transcript or honest "unavailable"
  POST /api/meetings/{id}/transcript           — manual/demo transcript → proposal

No fake tasks, no fake transcription: a proposal is created only when the
rule-based extractor finds an actual task in the text.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brain_api.api.routes.public_api import SimpleStore, get_store
from brain_api.demo.extractor import extract_task
from brain_api.demo.store import (
    VALID_TASK_STATUSES,
    BrainStore,
    dedupe_key,
    get_brain_store,
)
from brain_api.integrations.yougile import YouGileBoardService, get_yougile_service

router = APIRouter(prefix="/api", tags=["demo-brain"])


async def _apply_yougile_sync(
    brain: BrainStore, yougile: YouGileBoardService, task: dict[str, Any], *, on_move: bool
) -> dict[str, Any]:
    """Run a YouGile create/move sync and persist the result on the task.

    Local board is the source of truth: a "disabled" result is left untouched
    (when on_move) and a failed sync only records yougile_status="error".
    """
    if on_move:
        result = await yougile.sync_task_move(task, task["status"])
        if result.yougile_status == "disabled":
            return task  # YouGile off — keep local task as-is.
    else:
        result = await yougile.sync_task_on_confirm(task)
    updated = brain.update_task_yougile(
        task["task_id"],
        yougile_status=result.yougile_status,
        yougile_task_id=result.yougile_task_id,
        yougile_error=result.yougile_error,
    )
    return updated or task


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class ChatMessageRequest(BaseModel):
    chat_id: str = "demo-chat"
    message_id: str = ""
    author: str = ""
    text: str
    created_at: str = ""


class MoveTaskRequest(BaseModel):
    status: str


class TranscriptRequest(BaseModel):
    text: str
    speaker: str = ""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _proposal_view(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": p["proposal_id"],
        "status": p["status"],
        "title": p["title"],
        "assignee": p["assignee"],
        "deadline": p["deadline"],
        "description": p["description"],
        "source": p["source"],
        "confidence": p["confidence"],
    }


def _today() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# Chat → proposal
# --------------------------------------------------------------------------- #


@router.post("/chat/messages")
async def ingest_chat_message(
    body: ChatMessageRequest,
    brain: BrainStore = Depends(get_brain_store),
) -> dict[str, Any]:
    message_id = body.message_id or "msg_" + datetime.now(tz=UTC).strftime("%H%M%S%f")
    brain.save_message(
        {
            "message_id": message_id,
            "chat_id": body.chat_id,
            "author": body.author,
            "text": body.text,
            "created_at": body.created_at,
        }
    )

    extracted = extract_task(body.text, author=body.author, source="chat")
    if not extracted.has_task:
        return {"ok": True, "message_id": message_id, "has_task": False, "proposal": None}

    # Duplicate guard: same title + assignee + deadline among pending proposals.
    key = dedupe_key(extracted.title, extracted.assignee, extracted.deadline)
    existing = brain.find_duplicate(key)
    if existing is not None:
        return {
            "ok": True,
            "message_id": message_id,
            "duplicate": True,
            "existing_proposal_id": existing["proposal_id"],
        }

    proposal = brain.create_proposal(
        {
            "title": extracted.title,
            "assignee": extracted.assignee,
            "deadline": extracted.deadline,
            "description": extracted.description,
            "source": "chat",
            "confidence": extracted.confidence,
            "dedupe_key": key,
            "chat_id": body.chat_id,
            "message_id": message_id,
        }
    )
    return {
        "ok": True,
        "message_id": message_id,
        "has_task": True,
        "proposal": _proposal_view(proposal),
    }


# --------------------------------------------------------------------------- #
# Proposals
# --------------------------------------------------------------------------- #


@router.get("/task-proposals")
async def list_proposals(
    status: str | None = None,
    brain: BrainStore = Depends(get_brain_store),
) -> dict[str, Any]:
    return {"ok": True, "proposals": [_proposal_view(p) for p in brain.list_proposals(status)]}


@router.post("/task-proposals/{proposal_id}/confirm")
async def confirm_proposal(
    proposal_id: str,
    brain: BrainStore = Depends(get_brain_store),
    yougile: YouGileBoardService = Depends(get_yougile_service),
) -> dict[str, Any]:
    proposal = brain.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")

    # Idempotent: if already confirmed, return its task.
    if proposal["status"] == "confirmed" and proposal.get("task_id"):
        task = brain.get_task(proposal["task_id"])
        return {"ok": True, "proposal_id": proposal_id, "task": task}

    if proposal["status"] != "pending":
        raise HTTPException(
            status_code=400, detail=f"Proposal is '{proposal['status']}', cannot confirm"
        )

    task = brain.create_task_from_proposal(proposal)
    brain.set_proposal_status(proposal_id, "confirmed", task_id=task["task_id"])
    # Sync to YouGile (best-effort; local task stands regardless of result).
    task = await _apply_yougile_sync(brain, yougile, task, on_move=False)
    return {"ok": True, "proposal_id": proposal_id, "task": task}


@router.post("/task-proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    brain: BrainStore = Depends(get_brain_store),
) -> dict[str, Any]:
    proposal = brain.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found")

    if proposal["status"] == "confirmed":
        raise HTTPException(status_code=400, detail="Proposal already confirmed, cannot reject")

    brain.set_proposal_status(proposal_id, "rejected")
    return {"ok": True, "proposal_id": proposal_id, "status": "rejected"}


# --------------------------------------------------------------------------- #
# Tasks & board
# --------------------------------------------------------------------------- #


@router.get("/tasks")
async def list_tasks(brain: BrainStore = Depends(get_brain_store)) -> dict[str, Any]:
    return {"ok": True, "tasks": brain.list_tasks()}


@router.get("/board")
async def get_board(brain: BrainStore = Depends(get_brain_store)) -> dict[str, Any]:
    return {"ok": True, **brain.board()}


@router.post("/tasks/{task_id}/move")
async def move_task(
    task_id: str,
    body: MoveTaskRequest,
    brain: BrainStore = Depends(get_brain_store),
    yougile: YouGileBoardService = Depends(get_yougile_service),
) -> dict[str, Any]:
    if body.status not in VALID_TASK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{body.status}'. Allowed: {sorted(VALID_TASK_STATUSES)}",
        )
    task = brain.move_task(task_id, body.status)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    # Mirror the move into YouGile (best-effort; local move is not rolled back).
    task = await _apply_yougile_sync(brain, yougile, task, on_move=True)
    return {"ok": True, "task": task}


# --------------------------------------------------------------------------- #
# YouGile integration
# --------------------------------------------------------------------------- #


@router.get("/integrations/yougile/status")
async def yougile_status(
    yougile: YouGileBoardService = Depends(get_yougile_service),
) -> dict[str, Any]:
    cfg = yougile.config
    health = await yougile.health()
    return {
        "ok": True,
        "enabled": cfg.enabled,
        "configured": cfg.configured,
        "status": health.status,
        "reason": health.reason,
        "company_id": cfg.company_id,
        "project_id": cfg.project_id,
        "board_id": cfg.board_id,
    }


@router.get("/integrations/yougile/columns")
async def yougile_columns(
    yougile: YouGileBoardService = Depends(get_yougile_service),
) -> dict[str, Any]:
    data = await yougile.columns_status()
    return {"ok": True, **data}


@router.post("/tasks/{task_id}/sync-yougile")
async def sync_task_yougile(
    task_id: str,
    brain: BrainStore = Depends(get_brain_store),
    yougile: YouGileBoardService = Depends(get_yougile_service),
) -> dict[str, Any]:
    """Manually retry YouGile sync for a task (after an error or after enabling YouGile)."""
    task = brain.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    if not task.get("yougile_task_id"):
        # Never created in YouGile yet → create it now.
        task = await _apply_yougile_sync(brain, yougile, task, on_move=False)
    else:
        # Already exists → re-apply current column.
        result = await yougile.sync_task_move(task, task["status"])
        task = (
            brain.update_task_yougile(
                task_id,
                yougile_status=result.yougile_status,
                yougile_task_id=result.yougile_task_id,
                yougile_error=result.yougile_error,
            )
            or task
        )

    return {"ok": True, "task": task, "yougile": yougile.get_sync_status(task)}


# --------------------------------------------------------------------------- #
# Digest
# --------------------------------------------------------------------------- #


@router.get("/digest/evening")
async def evening_digest(brain: BrainStore = Depends(get_brain_store)) -> dict[str, Any]:
    today = _today()
    all_tasks = brain.list_tasks()
    created_today = [t for t in all_tasks if t.get("created_at", "").startswith(today)]
    pending = brain.list_proposals(status="pending")
    by_assignee = {
        assignee: [t["title"] for t in tasks]
        for assignee, tasks in brain.tasks_by_assignee().items()
    }
    return {
        "ok": True,
        "date": today,
        "created_today": [t["title"] for t in created_today],
        "pending_proposals": [_proposal_view(p) for p in pending],
        "overdue": [],  # no real deadline parsing into dates in demo store
        "by_assignee": by_assignee,
    }


# --------------------------------------------------------------------------- #
# Transcript (honest unavailable + manual demo injection)
# --------------------------------------------------------------------------- #


@router.get("/meetings/{meeting_id}/transcript")
async def get_transcript(
    meeting_id: str,
    brain: BrainStore = Depends(get_brain_store),
    store: SimpleStore = Depends(get_store),
) -> dict[str, Any]:
    lines = brain.get_transcript(meeting_id)
    if not lines:
        # No real STT provider is configured, and no manual transcript was injected.
        return {
            "ok": True,
            "meeting_id": meeting_id,
            "transcription_status": "unavailable",
            "reason": "STT provider is not configured",
            "lines": [],
        }
    return {
        "ok": True,
        "meeting_id": meeting_id,
        "transcription_status": "available",
        "source": "manual",
        "lines": lines,
    }


@router.post("/meetings/{meeting_id}/transcript")
async def post_transcript(
    meeting_id: str,
    body: TranscriptRequest,
    brain: BrainStore = Depends(get_brain_store),
    store: SimpleStore = Depends(get_store),
) -> dict[str, Any]:
    # Ensure the meeting exists in the shared store (manual/demo transcript).
    store.ensure_meeting(meeting_id, source="telemost_bot")

    brain.add_transcript_line(meeting_id, body.text, body.speaker)

    # Run the SAME extractor as chat — this is manual transcript input, not fake STT.
    extracted = extract_task(body.text, author=body.speaker, source="meeting_transcript")
    if not extracted.has_task:
        return {
            "ok": True,
            "meeting_id": meeting_id,
            "has_task": False,
            "proposal": None,
        }

    key = dedupe_key(extracted.title, extracted.assignee, extracted.deadline)
    existing = brain.find_duplicate(key)
    if existing is not None:
        return {
            "ok": True,
            "meeting_id": meeting_id,
            "duplicate": True,
            "existing_proposal_id": existing["proposal_id"],
        }

    proposal = brain.create_proposal(
        {
            "title": extracted.title,
            "assignee": extracted.assignee,
            "deadline": extracted.deadline,
            "description": extracted.description,
            "source": "meeting_transcript",
            "confidence": extracted.confidence,
            "dedupe_key": key,
            "meeting_id": meeting_id,
        }
    )
    return {
        "ok": True,
        "meeting_id": meeting_id,
        "has_task": True,
        "proposal": _proposal_view(proposal),
    }
