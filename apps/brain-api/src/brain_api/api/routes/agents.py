"""Account / workspace / daemon (agent) pairing + ownership API.

  GET  /api/profile                     — current demo account/workspace
  POST /api/agents/pairing-code         — one-time, time-limited pairing code
  POST /api/agents/register             — daemon registers with a pairing code
  GET  /api/agents                      — agents of a workspace + status
  POST /api/agents/heartbeat            — daemon heartbeat (X-Agent-Token)
  POST /api/agents/{agent_id}/unpair    — remove an agent from the workspace
  POST /api/daemon/uploads              — daemon upload, owned by token→workspace
  GET  /api/daemon/uploads              — uploads of a workspace

Daemon endpoints authenticate with the agent_token (X-Agent-Token or
Authorization: Bearer) obtained at registration — never the INTERNAL_API_TOKEN.
The legacy POST /api/audio/upload remains for the existing smoke flow.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import BaseModel

from brain_api.demo.agents import AgentsStore, get_agents_store
from brain_api.demo.extractor import extract_task
from brain_api.demo.store import BrainStore, dedupe_key, get_brain_store

router = APIRouter(prefix="/api", tags=["agents"])


def _backend_url(request: Request) -> str:
    configured = os.getenv("PUBLIC_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    domain = os.getenv("DOMAIN", "").strip()
    if domain:
        return f"https://{domain}"
    return str(request.base_url).rstrip("/")


def _auth_agent(
    store: AgentsStore,
    x_agent_token: str | None,
    authorization: str | None,
) -> dict[str, Any]:
    token = x_agent_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    agent = store.agent_by_token(token)
    if agent is None:
        raise HTTPException(status_code=401, detail="invalid or missing agent token")
    return agent


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #
@router.get("/profile")
async def get_profile(
    request: Request,
    workspace_id: str | None = None,
    store: AgentsStore = Depends(get_agents_store),
) -> dict[str, Any]:
    return {"ok": True, **store.profile(workspace_id, _backend_url(request))}


# --------------------------------------------------------------------------- #
# Pairing
# --------------------------------------------------------------------------- #
class PairingCodeRequest(BaseModel):
    workspace_id: str | None = None


@router.post("/agents/pairing-code")
async def create_pairing_code(
    body: PairingCodeRequest | None = None,
    store: AgentsStore = Depends(get_agents_store),
) -> dict[str, Any]:
    workspace_id = body.workspace_id if body else None
    return {"ok": True, **store.create_pairing_code(workspace_id)}


class RegisterAgentRequest(BaseModel):
    pairing_code: str
    device_name: str = ""
    os: str = "windows"
    daemon_version: str = ""


@router.post("/agents/register")
async def register_agent(
    body: RegisterAgentRequest,
    request: Request,
    store: AgentsStore = Depends(get_agents_store),
) -> dict[str, Any]:
    try:
        result = store.register_agent(
            body.pairing_code, body.device_name, body.os, body.daemon_version
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "backend_url": _backend_url(request), **result}


# --------------------------------------------------------------------------- #
# Agents listing / heartbeat / unpair
# --------------------------------------------------------------------------- #
@router.get("/agents")
async def list_agents(
    workspace_id: str | None = None,
    store: AgentsStore = Depends(get_agents_store),
) -> dict[str, Any]:
    return {"ok": True, "agents": store.list_agents(workspace_id)}


class HeartbeatRequest(BaseModel):
    agent_id: str | None = None
    status: str = "idle"
    version: str | None = None
    device_name: str | None = None


@router.post("/agents/heartbeat")
async def heartbeat(
    body: HeartbeatRequest,
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    authorization: str | None = Header(default=None),
    store: AgentsStore = Depends(get_agents_store),
) -> dict[str, Any]:
    agent = _auth_agent(store, x_agent_token, authorization)
    view = store.heartbeat(agent, body.status, body.version, body.device_name)
    return {"ok": True, "agent": view}


@router.post("/agents/{agent_id}/unpair")
async def unpair_agent(
    agent_id: str,
    workspace_id: str | None = None,
    store: AgentsStore = Depends(get_agents_store),
) -> dict[str, Any]:
    if not store.unpair(workspace_id, agent_id):
        raise HTTPException(status_code=404, detail="agent not found in workspace")
    return {"ok": True, "agent_id": agent_id, "unpaired": True}


# --------------------------------------------------------------------------- #
# Daemon uploads (owned by token → workspace)
# --------------------------------------------------------------------------- #
_log = logging.getLogger(__name__)


async def _transcribe_wav(content: bytes) -> str:
    """Transcribe a recorded WAV via asr-service (faster-whisper). Best-effort:
    on any error returns "" so the upload still succeeds."""
    url = os.getenv("ASR_SERVICE_URL", "http://asr-service:8030/transcribe")
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(url, content=content, headers={"Content-Type": "audio/wav"})
            resp.raise_for_status()
            return (resp.json().get("text") or "").strip()
    except Exception as exc:  # noqa: BLE001 — transcription must never break upload
        _log.warning("asr transcription failed: %s", exc)
        return ""


def _maybe_create_proposal(brain: BrainStore, transcript_text: str) -> dict[str, Any] | None:
    """If the recording carried a transcript with an action item, propose a task."""
    text = (transcript_text or "").strip()
    if not text:
        return None
    extracted = extract_task(text, source="meeting")
    if not extracted.has_task:
        return None
    key = dedupe_key(extracted.title, extracted.assignee, extracted.deadline)
    existing = brain.find_duplicate(key)
    if existing is not None:
        return existing
    return brain.create_proposal(
        {
            "title": extracted.title,
            "assignee": extracted.assignee,
            "deadline": extracted.deadline,
            "description": extracted.description,
            "source": "meeting",
            "confidence": extracted.confidence,
            "dedupe_key": key,
        }
    )


@router.post("/daemon/uploads")
async def daemon_upload(
    request: Request,
    audio: UploadFile | None = File(default=None),
    recording_id: str = Form(default=""),
    started_at: str = Form(default=""),
    stopped_at: str = Form(default=""),
    duration_sec: float = Form(default=0),
    source: str = Form(default="microphone"),
    transcript_text: str = Form(default=""),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    authorization: str | None = Header(default=None),
    store: AgentsStore = Depends(get_agents_store),
    brain: BrainStore = Depends(get_brain_store),
) -> dict[str, Any]:
    agent = _auth_agent(store, x_agent_token, authorization)

    size_bytes = 0
    filename = ""
    content = b""
    if audio is not None:
        uploads_dir = Path(os.getenv("UPLOADS_DIR", "/tmp/gc-uploads")) / "daemon"
        uploads_dir = uploads_dir / agent["workspace_id"] / agent["agent_id"]
        uploads_dir.mkdir(parents=True, exist_ok=True)
        content = await audio.read()
        size_bytes = len(content)
        filename = audio.filename or f"{recording_id or 'recording'}.wav"
        (uploads_dir / filename).write_bytes(content)

    # Real processing: if the daemon didn't send a transcript, transcribe the
    # recorded audio with asr-service (faster-whisper), then extract a task.
    if not transcript_text.strip() and size_bytes > 64:
        transcript_text = await _transcribe_wav(content)

    proposal = _maybe_create_proposal(brain, transcript_text)

    upload = store.record_upload(
        agent,
        {
            "recording_id": recording_id,
            "started_at": started_at,
            "stopped_at": stopped_at,
            "duration_sec": duration_sec,
            "source": source,
            "filename": filename,
            "size_bytes": size_bytes,
            "transcript_text": transcript_text,
            "proposal_id": proposal["proposal_id"] if proposal else "",
        },
    )
    return {
        "ok": True,
        "upload_id": upload["upload_id"],
        "agent_id": agent["agent_id"],
        "workspace_id": agent["workspace_id"],
        "proposal_created": proposal is not None,
        "proposal_id": proposal["proposal_id"] if proposal else "",
    }


@router.get("/daemon/uploads")
async def list_daemon_uploads(
    workspace_id: str | None = None,
    store: AgentsStore = Depends(get_agents_store),
) -> dict[str, Any]:
    return {"ok": True, "uploads": store.list_uploads(workspace_id)}
