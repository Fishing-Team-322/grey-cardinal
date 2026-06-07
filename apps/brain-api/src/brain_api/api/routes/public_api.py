"""Legacy public demo API used by smoke tests."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/api", tags=["public-demo"])


class SimpleStore:
    def __init__(self, uploads_dir: Path) -> None:
        self.uploads_dir = Path(uploads_dir)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.uploads_dir / "meetings.json"
        self._state: dict[str, dict[str, dict]] = {"meetings": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self._state = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = self.path.with_suffix(f".json.corrupt-{datetime.now(UTC).timestamp()}.bak")
            shutil.copyfile(self.path, backup)
            self._state = {"meetings": {}}

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def ensure_meeting(
        self,
        meeting_id: str,
        *,
        source: str = "desktop_agent",
        agent_id: str = "",
        started_at: str = "",
        ended_at: str = "",
    ) -> dict:
        meetings = self._state.setdefault("meetings", {})
        meeting = meetings.get(meeting_id)
        if meeting is None:
            meeting = {
                "meeting_id": meeting_id,
                "status": "uploaded",
                "source": source,
                "agent_id": agent_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "created_at": datetime.now(UTC).isoformat(),
                "audios": [],
                "tasks": [],
            }
            meetings[meeting_id] = meeting
            self._save()
        return meeting

    def add_audio(
        self,
        meeting_id: str,
        audio_id: str,
        filename: str,
        agent_id: str,
        started_at: str,
        ended_at: str,
    ) -> dict:
        meeting = self.ensure_meeting(
            meeting_id,
            agent_id=agent_id,
            started_at=started_at,
            ended_at=ended_at,
        )
        audio = {
            "audio_id": audio_id,
            "filename": filename,
            "agent_id": agent_id,
            "status": "uploaded",
            "created_at": datetime.now(UTC).isoformat(),
        }
        meeting["audios"].append(audio)
        meeting["status"] = "uploaded"
        self._save()
        return audio

    def list_meetings(self) -> list[dict]:
        return list(self._state.get("meetings", {}).values())

    def get_meeting(self, meeting_id: str) -> dict | None:
        return self._state.get("meetings", {}).get(meeting_id)


_store = SimpleStore(Path(".gc_uploads"))


def set_store(store: SimpleStore) -> None:
    global _store
    _store = store


def get_store() -> SimpleStore:
    return _store


@router.get("/health")
async def public_health() -> dict:
    return {"ok": True, "service": "backend", "status": "running"}


@router.post("/audio/upload")
async def upload_audio(
    agent_id: str = Form(""),
    meeting_id: str = Form(""),
    source: str = Form("desktop_agent"),
    started_at: str = Form(""),
    ended_at: str = Form(""),
    audio: UploadFile = File(...),
    store: SimpleStore = Depends(get_store),
) -> dict:
    if source not in {"desktop_agent", "telemost_bot"}:
        raise HTTPException(400, "Unknown source")
    mid = meeting_id or f"meeting_{uuid4().hex}"
    store.ensure_meeting(
        mid,
        source=source,
        agent_id=agent_id,
        started_at=started_at,
        ended_at=ended_at,
    )
    audio_id = f"audio_{uuid4().hex}"
    target = store.uploads_dir / f"{audio_id}_{audio.filename or 'audio.wav'}"
    target.write_bytes(await audio.read())
    store.add_audio(
        audio_id=audio_id,
        meeting_id=mid,
        filename=audio.filename or "",
        agent_id=agent_id,
        started_at=started_at,
        ended_at=ended_at,
    )
    return {
        "ok": True,
        "audio_id": audio_id,
        "meeting_id": mid,
        "status": "uploaded",
        "message": "Audio uploaded successfully",
    }


@router.get("/meetings")
async def list_meetings(store: SimpleStore = Depends(get_store)) -> dict:
    meetings = []
    for meeting in store.list_meetings():
        meetings.append(
            {
                "meeting_id": meeting["meeting_id"],
                "status": meeting["status"],
                "source": meeting["source"],
                "created_at": meeting["created_at"],
                "audio_count": len(meeting.get("audios", [])),
                "tasks_count": len(meeting.get("tasks", [])),
            }
        )
    return {"ok": True, "meetings": meetings}


@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str, store: SimpleStore = Depends(get_store)) -> dict:
    meeting = store.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return {"ok": True, "meeting": meeting}


@router.get("/meetings/{meeting_id}/status")
async def meeting_status(meeting_id: str, store: SimpleStore = Depends(get_store)) -> dict:
    meeting = store.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return {"ok": True, "meeting_id": meeting_id, "status": meeting["status"]}


@router.get("/meetings/{meeting_id}/tasks")
async def meeting_tasks(meeting_id: str, store: SimpleStore = Depends(get_store)) -> dict:
    meeting = store.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return {"ok": True, "meeting_id": meeting_id, "tasks": meeting.get("tasks", [])}
