"""Tests for public /api/* endpoints.

Run:
    cd apps/brain-api
    pytest tests/test_public_api.py -v

These tests use TestClient (synchronous) and an in-memory SimpleStore
so they do NOT require PostgreSQL or any external services.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.routes.public_api import SimpleStore, get_store, router, set_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_store(tmp_path: Path) -> SimpleStore:
    store = SimpleStore(tmp_path / "uploads")
    set_store(store)
    return store


@pytest.fixture
def app(tmp_store: SimpleStore) -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    # Override the store dependency for isolation.
    application.dependency_overrides[get_store] = lambda: tmp_store
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _wav_bytes() -> bytes:
    """Minimal valid 44-byte WAV header with no audio data."""
    import struct
    header = b"RIFF" + struct.pack("<I", 36) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
    header += b"data" + struct.pack("<I", 0)
    return header


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_returns_ok(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["service"] == "backend"
    assert body["status"] == "running"


# ---------------------------------------------------------------------------
# Audio upload
# ---------------------------------------------------------------------------

def test_upload_creates_meeting_auto_id(client: TestClient) -> None:
    r = client.post(
        "/api/audio/upload",
        data={"agent_id": "agent-001", "source": "desktop_agent"},
        files={"audio": ("rec.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["audio_id"].startswith("audio_")
    assert body["meeting_id"]  # auto-generated
    assert body["status"] == "uploaded"
    assert body["message"] == "Audio uploaded successfully"


def test_upload_uses_provided_meeting_id(client: TestClient) -> None:
    r = client.post(
        "/api/audio/upload",
        data={
            "agent_id": "agent-001",
            "meeting_id": "my-meeting-42",
            "source": "desktop_agent",
            "started_at": "2026-06-03T10:00:00Z",
            "ended_at": "2026-06-03T10:05:00Z",
        },
        files={"audio": ("rec.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["meeting_id"] == "my-meeting-42"


def test_upload_without_file_returns_error(client: TestClient) -> None:
    r = client.post("/api/audio/upload", data={"agent_id": "agent-001"})
    assert r.status_code == 422  # Unprocessable Entity — file field required


def test_upload_appears_in_meetings_list(client: TestClient) -> None:
    client.post(
        "/api/audio/upload",
        data={"agent_id": "a1", "meeting_id": "meet-listed"},
        files={"audio": ("r.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    r = client.get("/api/meetings")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    ids = [m["meeting_id"] for m in body["meetings"]]
    assert "meet-listed" in ids


def test_upload_increments_audio_count(client: TestClient) -> None:
    mid = "meet-audio-count"
    for _ in range(3):
        client.post(
            "/api/audio/upload",
            data={"agent_id": "a1", "meeting_id": mid},
            files={"audio": ("r.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
        )
    r = client.get("/api/meetings")
    meeting = next(m for m in r.json()["meetings"] if m["meeting_id"] == mid)
    assert meeting["audio_count"] == 3


# ---------------------------------------------------------------------------
# Meetings list
# ---------------------------------------------------------------------------

def test_meetings_empty_initially(client: TestClient) -> None:
    r = client.get("/api/meetings")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["meetings"] == []


def test_meetings_list_contains_required_fields(client: TestClient) -> None:
    client.post(
        "/api/audio/upload",
        data={"agent_id": "a1", "meeting_id": "meet-fields"},
        files={"audio": ("r.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    r = client.get("/api/meetings")
    meeting = r.json()["meetings"][0]
    assert "meeting_id" in meeting
    assert "status" in meeting
    assert "source" in meeting
    assert "created_at" in meeting
    assert "audio_count" in meeting
    assert "tasks_count" in meeting


# ---------------------------------------------------------------------------
# Get single meeting
# ---------------------------------------------------------------------------

def test_get_meeting_returns_detail(client: TestClient) -> None:
    client.post(
        "/api/audio/upload",
        data={
            "agent_id": "a1",
            "meeting_id": "meet-detail",
            "started_at": "2026-06-03T10:00:00Z",
            "ended_at": "2026-06-03T10:05:00Z",
        },
        files={"audio": ("r.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    r = client.get("/api/meetings/meet-detail")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    m = body["meeting"]
    assert m["meeting_id"] == "meet-detail"
    assert isinstance(m["audios"], list)
    assert len(m["audios"]) == 1
    assert isinstance(m["tasks"], list)


def test_get_meeting_unknown_returns_404(client: TestClient) -> None:
    r = client.get("/api/meetings/does-not-exist")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Meeting status
# ---------------------------------------------------------------------------

def test_meeting_status_after_upload(client: TestClient) -> None:
    client.post(
        "/api/audio/upload",
        data={"agent_id": "a1", "meeting_id": "meet-status"},
        files={"audio": ("r.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    r = client.get("/api/meetings/meet-status/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["meeting_id"] == "meet-status"
    assert body["status"] == "uploaded"


def test_meeting_status_unknown_returns_404(client: TestClient) -> None:
    r = client.get("/api/meetings/ghost-meeting/status")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tasks (stub)
# ---------------------------------------------------------------------------

def test_meeting_tasks_returns_empty_list(client: TestClient) -> None:
    client.post(
        "/api/audio/upload",
        data={"agent_id": "a1", "meeting_id": "meet-tasks"},
        files={"audio": ("r.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    r = client.get("/api/meetings/meet-tasks/tasks")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["meeting_id"] == "meet-tasks"
    assert body["tasks"] == []


def test_meeting_tasks_unknown_returns_404(client: TestClient) -> None:
    r = client.get("/api/meetings/ghost-tasks/tasks")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# SimpleStore unit tests (no HTTP)
# ---------------------------------------------------------------------------

def test_store_creates_meeting_on_first_upload(tmp_path: Path) -> None:
    store = SimpleStore(tmp_path / "uploads")
    meeting = store.ensure_meeting("m1", source="desktop_agent", agent_id="a1")
    assert meeting["meeting_id"] == "m1"
    assert meeting["status"] == "uploaded"


def test_store_reuses_existing_meeting(tmp_path: Path) -> None:
    store = SimpleStore(tmp_path / "uploads")
    store.ensure_meeting("m1", source="desktop_agent", agent_id="a1")
    m_again = store.ensure_meeting("m1", source="other", agent_id="a2")
    # Source should NOT be overwritten on second call.
    assert m_again["source"] == "desktop_agent"


def test_store_persists_to_json(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    store1 = SimpleStore(uploads)
    store1.ensure_meeting("persist-m", source="desktop_agent", agent_id="a1")
    store1.add_audio("persist-m", "aud-1", "rec.wav", "a1", "", "")

    # Reload from disk.
    store2 = SimpleStore(uploads)
    meeting = store2.get_meeting("persist-m")
    assert meeting is not None
    assert len(meeting["audios"]) == 1
