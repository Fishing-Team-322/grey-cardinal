"""Public API routes для desktop agent и frontend dashboard.

Endpoints:
  GET  /api/health
  POST /api/audio/upload
  GET  /api/meetings
  GET  /api/meetings/{meeting_id}
  GET  /api/meetings/{meeting_id}/status
  GET  /api/meetings/{meeting_id}/tasks

Хранение:
  - Аудиофайлы: {UPLOADS_DIR}/{meeting_id}/{audio_id}.wav
  - Метаданные: {UPLOADS_DIR}/metadata.json (также держится в памяти)

Не зависит от PostgreSQL и Container — работает автономно для демо.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

# ---------------------------------------------------------------------------
# Simple file-backed store
# ---------------------------------------------------------------------------


class SimpleStore:
    """Хранит метаданные встреч и аудиофайлов в JSON + на диске."""

    def __init__(self, uploads_dir: Path) -> None:
        self.uploads_dir = uploads_dir
        self._meta_path = uploads_dir / "metadata.json"
        self._meetings: dict[str, dict[str, Any]] = {}
        self._audios: dict[str, dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if self._meta_path.exists():
            try:
                data = json.loads(self._meta_path.read_text(encoding="utf-8"))
                self._meetings = data.get("meetings", {})
                self._audios = data.get("audios", {})
            except Exception:
                pass

    def _save(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path.write_text(
            json.dumps(
                {"meetings": self._meetings, "audios": self._audios}, indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def ensure_meeting(
        self,
        meeting_id: str,
        source: str = "desktop_agent",
        agent_id: str = "",
    ) -> dict[str, Any]:
        """Возвращает встречу, создаёт если не было."""
        if meeting_id not in self._meetings:
            self._meetings[meeting_id] = {
                "meeting_id": meeting_id,
                "status": "uploaded",
                "source": source,
                "agent_id": agent_id,
                "created_at": self._now_iso(),
                "audio_ids": [],
            }
        return self._meetings[meeting_id]

    def add_audio(
        self,
        meeting_id: str,
        audio_id: str,
        filename: str,
        agent_id: str,
        started_at: str,
        ended_at: str,
    ) -> dict[str, Any]:
        audio: dict[str, Any] = {
            "audio_id": audio_id,
            "meeting_id": meeting_id,
            "filename": filename,
            "agent_id": agent_id,
            "status": "uploaded",
            "started_at": started_at,
            "ended_at": ended_at,
            "created_at": self._now_iso(),
        }
        self._audios[audio_id] = audio
        meeting = self._meetings.get(meeting_id, {})
        if meeting and audio_id not in meeting.get("audio_ids", []):
            meeting.setdefault("audio_ids", []).append(audio_id)
        self._save()
        return audio

    def list_meetings(self) -> list[dict[str, Any]]:
        rows = []
        for m in self._meetings.values():
            rows.append(
                {
                    "meeting_id": m["meeting_id"],
                    "status": m.get("status", "uploaded"),
                    "source": m.get("source", "desktop_agent"),
                    "created_at": m.get("created_at", ""),
                    "audio_count": len(m.get("audio_ids", [])),
                    "tasks_count": 0,
                }
            )
        rows.sort(key=lambda x: x["created_at"], reverse=True)
        return rows

    def get_meeting(self, meeting_id: str) -> dict[str, Any] | None:
        m = self._meetings.get(meeting_id)
        if m is None:
            return None
        audios = [self._audios[aid] for aid in m.get("audio_ids", []) if aid in self._audios]
        return {
            "meeting_id": m["meeting_id"],
            "status": m.get("status", "uploaded"),
            "source": m.get("source", "desktop_agent"),
            "created_at": m.get("created_at", ""),
            "audios": audios,
            "tasks": [],
        }

    def audio_file_path(self, meeting_id: str, audio_id: str) -> Path:
        return self.uploads_dir / meeting_id / f"{audio_id}.wav"

    def set_meeting_error(self, meeting_id: str, error: str) -> None:
        if meeting_id in self._meetings:
            self._meetings[meeting_id]["status"] = "error"
            self._meetings[meeting_id]["error"] = error
            self._save()


# ---------------------------------------------------------------------------
# Store singleton (lazy init, overridable in tests)
# ---------------------------------------------------------------------------

_store: SimpleStore | None = None


def get_store() -> SimpleStore:
    global _store
    if _store is None:
        uploads_dir = Path(os.getenv("UPLOADS_DIR", "/tmp/gc-uploads"))
        _store = SimpleStore(uploads_dir)
    return _store


def set_store(store: SimpleStore) -> None:
    """Заменить store — используется в тестах."""
    global _store
    _store = store


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["public-api"])


@router.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "backend", "status": "running"}


@router.head("/health", include_in_schema=False)
async def health_head() -> Response:
    return Response(status_code=200)


@router.post("/audio/upload")
async def upload_audio(
    audio: UploadFile = File(..., description="WAV audio file"),
    agent_id: str = Form(default="", description="Agent identifier"),
    meeting_id: str = Form(default="", description="Meeting ID; auto-created if empty"),
    source: str = Form(default="desktop_agent"),
    started_at: str = Form(default=""),
    ended_at: str = Form(default=""),
    store: SimpleStore = Depends(get_store),
) -> dict[str, Any]:
    # Validate source field.
    _ALLOWED_SOURCES = {"desktop_agent", "telemost_bot"}
    if source not in _ALLOWED_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source '{source}'. Allowed: {sorted(_ALLOWED_SOURCES)}",
        )

    # Generate IDs if not provided.
    if not meeting_id:
        meeting_id = str(uuid.uuid4())
    audio_id = "audio_" + str(uuid.uuid4()).replace("-", "")[:12]

    # Ensure meeting exists.
    store.ensure_meeting(meeting_id, source=source, agent_id=agent_id)

    # Save file to disk.
    file_path = store.audio_file_path(meeting_id, audio_id)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        content = await audio.read()
        file_path.write_bytes(content)
    except Exception as exc:
        store.set_meeting_error(meeting_id, str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to save audio: {exc}") from exc

    # Store metadata.
    filename = audio.filename or f"{audio_id}.wav"
    store.add_audio(
        meeting_id=meeting_id,
        audio_id=audio_id,
        filename=filename,
        agent_id=agent_id,
        started_at=started_at,
        ended_at=ended_at,
    )

    return {
        "ok": True,
        "audio_id": audio_id,
        "meeting_id": meeting_id,
        "status": "uploaded",
        "message": "Audio uploaded successfully",
    }


@router.get("/meetings")
async def list_meetings(store: SimpleStore = Depends(get_store)) -> dict[str, Any]:
    return {"ok": True, "meetings": store.list_meetings()}


@router.get("/meetings/{meeting_id}")
async def get_meeting(
    meeting_id: str,
    store: SimpleStore = Depends(get_store),
) -> dict[str, Any]:
    meeting = store.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found")
    return {"ok": True, "meeting": meeting}


@router.get("/meetings/{meeting_id}/status")
async def get_meeting_status(
    meeting_id: str,
    store: SimpleStore = Depends(get_store),
) -> dict[str, Any]:
    meeting = store.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found")
    return {
        "ok": True,
        "meeting_id": meeting_id,
        "status": meeting["status"],
    }


@router.get("/meetings/{meeting_id}/tasks")
async def get_meeting_tasks(
    meeting_id: str,
    store: SimpleStore = Depends(get_store),
) -> dict[str, Any]:
    meeting = store.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found")
    return {
        "ok": True,
        "meeting_id": meeting_id,
        "tasks": [],  # Заглушка — реальный AI-pipeline на backend, пока не подключён
    }
