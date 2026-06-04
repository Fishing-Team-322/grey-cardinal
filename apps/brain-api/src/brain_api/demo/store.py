"""In-memory + JSON-backed store for the demo brain pipeline.

Holds messages, task proposals, tasks and the board. Autonomous: no DB.
Mirrors the SimpleStore pattern (get_store / set_store) for test isolation.

This is a REAL store: proposals and tasks are persisted to disk and survive
restarts. It is not a mock — it just isn't PostgreSQL.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Board columns (statuses) — fixed for the demo.
BOARD_COLUMNS: list[tuple[str, str]] = [
    ("todo", "To do"),
    ("in_progress", "In progress"),
    ("done", "Done"),
]
VALID_TASK_STATUSES = {col_id for col_id, _ in BOARD_COLUMNS}


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def dedupe_key(title: str, assignee: str, deadline: str) -> str:
    return f"{_norm(title)}|{_norm(assignee)}|{_norm(deadline)}"


class BrainStore:
    """Demo brain store: messages, proposals, tasks, transcripts."""

    def __init__(self, base_dir: Path, file_name: str = "brain.json") -> None:
        self.base_dir = Path(base_dir)
        self._path = self.base_dir / file_name
        self._lock = threading.RLock()
        self._messages: dict[str, dict[str, Any]] = {}
        self._proposals: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, dict[str, Any]] = {}
        self._transcripts: dict[str, list[dict[str, Any]]] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence (atomic write + corruption backup + lock)
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._lock:
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                # Corrupted store: back it up and start clean so the app still boots.
                self._backup_corrupt()
                logger.warning("brain store corrupted (%s) — backed up and starting fresh", exc)
                return
            self._messages = data.get("messages", {})
            self._proposals = data.get("proposals", {})
            self._tasks = data.get("tasks", {})
            self._transcripts = data.get("transcripts", {})

    def _backup_corrupt(self) -> None:
        try:
            ts = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
            backup = self._path.with_name(self._path.name + f".corrupt-{ts}.bak")
            shutil.copy2(self._path, backup)
            logger.warning("brain store backup written: %s", backup)
        except OSError:
            pass

    def _save(self) -> None:
        payload = json.dumps(
            {
                "messages": self._messages,
                "proposals": self._proposals,
                "tasks": self._tasks,
                "transcripts": self._transcripts,
            },
            indent=2,
            ensure_ascii=False,
        )
        with self._lock:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            # Atomic write: write to a temp file in the same dir, then os.replace.
            fd, tmp = tempfile.mkstemp(dir=str(self.base_dir), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp, self._path)
            except OSError:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise

    # ------------------------------------------------------------------ #
    # Messages
    # ------------------------------------------------------------------ #

    def save_message(self, message: dict[str, Any]) -> None:
        mid = message.get("message_id") or uuid.uuid4().hex
        self._messages[mid] = {**message, "message_id": mid, "stored_at": _now_iso()}
        self._save()

    # ------------------------------------------------------------------ #
    # Proposals
    # ------------------------------------------------------------------ #

    def find_duplicate(self, key: str) -> dict[str, Any] | None:
        """Return an existing non-rejected proposal with the same dedupe key.

        Matches both pending and confirmed proposals, so re-sending the same
        task (even after it was confirmed) does not create a duplicate.
        """
        for p in self._proposals.values():
            if p.get("status") in ("pending", "confirmed") and p.get("dedupe_key") == key:
                return p
        return None

    def create_proposal(self, fields: dict[str, Any]) -> dict[str, Any]:
        proposal_id = "proposal_" + uuid.uuid4().hex[:12]
        proposal = {
            "proposal_id": proposal_id,
            "status": "pending",
            "title": fields.get("title", ""),
            "assignee": fields.get("assignee", ""),
            "deadline": fields.get("deadline", ""),
            "description": fields.get("description", ""),
            "source": fields.get("source", "chat"),
            "confidence": fields.get("confidence", 0.0),
            "dedupe_key": fields.get("dedupe_key", ""),
            "meeting_id": fields.get("meeting_id", ""),
            "chat_id": fields.get("chat_id", ""),
            "message_id": fields.get("message_id", ""),
            "created_at": _now_iso(),
            "task_id": "",
        }
        self._proposals[proposal_id] = proposal
        self._save()
        return proposal

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        return self._proposals.get(proposal_id)

    def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        rows = list(self._proposals.values())
        if status:
            rows = [p for p in rows if p.get("status") == status]
        rows.sort(key=lambda p: p.get("created_at", ""), reverse=True)
        return rows

    def set_proposal_status(self, proposal_id: str, status: str, task_id: str = "") -> None:
        p = self._proposals.get(proposal_id)
        if p:
            p["status"] = status
            if task_id:
                p["task_id"] = task_id
            self._save()

    # ------------------------------------------------------------------ #
    # Tasks
    # ------------------------------------------------------------------ #

    def create_task_from_proposal(self, proposal: dict[str, Any]) -> dict[str, Any]:
        task_id = "task_" + uuid.uuid4().hex[:12]
        task = {
            "task_id": task_id,
            "title": proposal.get("title", ""),
            "assignee": proposal.get("assignee", ""),
            "deadline": proposal.get("deadline", ""),
            "description": proposal.get("description", ""),
            "source": proposal.get("source", ""),
            "status": "todo",
            "proposal_id": proposal.get("proposal_id", ""),
            "meeting_id": proposal.get("meeting_id", ""),
            "chat_id": proposal.get("chat_id", ""),
            "confidence": proposal.get("confidence", 0.0),
            "yougile_task_id": "",
            "yougile_status": "disabled",
            "yougile_error": "",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        self._tasks[task_id] = task
        self._save()
        return task

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[dict[str, Any]]:
        rows = list(self._tasks.values())
        rows.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return rows

    def move_task(self, task_id: str, status: str) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task["status"] = status
        task["updated_at"] = _now_iso()
        self._save()
        return task

    def update_task_yougile(
        self,
        task_id: str,
        *,
        yougile_status: str,
        yougile_task_id: str | None = None,
        yougile_error: str = "",
    ) -> dict[str, Any] | None:
        """Persist YouGile sync fields on a task. Keeps existing task_id if not given."""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task["yougile_status"] = yougile_status
        if yougile_task_id:
            task["yougile_task_id"] = yougile_task_id
        task["yougile_error"] = yougile_error
        task["updated_at"] = _now_iso()
        self._save()
        return task

    def board(self) -> dict[str, Any]:
        columns = []
        for col_id, title in BOARD_COLUMNS:
            tasks = [t for t in self._tasks.values() if t.get("status") == col_id]
            tasks.sort(key=lambda t: t.get("created_at", ""))
            columns.append({"id": col_id, "title": title, "tasks": tasks})
        return {"columns": columns}

    # ------------------------------------------------------------------ #
    # Transcripts
    # ------------------------------------------------------------------ #

    def add_transcript_line(self, meeting_id: str, text: str, speaker: str) -> dict[str, Any]:
        line = {"text": text, "speaker": speaker, "created_at": _now_iso()}
        self._transcripts.setdefault(meeting_id, []).append(line)
        self._save()
        return line

    def get_transcript(self, meeting_id: str) -> list[dict[str, Any]]:
        return self._transcripts.get(meeting_id, [])

    # ------------------------------------------------------------------ #
    # Digest helpers
    # ------------------------------------------------------------------ #

    def tasks_by_assignee(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for t in self._tasks.values():
            key = t.get("assignee") or "unassigned"
            result.setdefault(key, []).append(t)
        return result


# --------------------------------------------------------------------------- #
# Singleton (overridable in tests)
# --------------------------------------------------------------------------- #

_store: BrainStore | None = None


def get_brain_store() -> BrainStore:
    global _store
    if _store is None:
        store_path = os.getenv("BRAIN_STORE_PATH", "").strip()
        if store_path:
            p = Path(store_path)
            _store = BrainStore(p.parent or Path("."), p.name)
        else:
            base = Path(os.getenv("UPLOADS_DIR", "/tmp/gc-uploads")) / "brain"
            _store = BrainStore(base)
    return _store


def set_brain_store(store: BrainStore) -> None:
    global _store
    _store = store
