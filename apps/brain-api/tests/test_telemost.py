"""Tests for Telemost bot session endpoints and audio upload source validation.

Run:
    cd apps/brain-api
    pytest tests/test_telemost.py -v
"""

from __future__ import annotations

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.routes.public_api import SimpleStore, get_store, set_store
from brain_api.api.routes.public_api import router as public_router
from brain_api.api.routes.telemost import router as telemost_router
from brain_api.api.routes.telemost import session_manager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_sessions():
    """Clear in-memory bot sessions between tests."""
    session_manager.clear_all()
    yield
    session_manager.clear_all()


@pytest.fixture
def tmp_store(tmp_path):
    store = SimpleStore(tmp_path / "uploads")
    set_store(store)
    return store


@pytest.fixture
def app(tmp_store):
    application = FastAPI()
    application.include_router(public_router)
    application.include_router(telemost_router)
    application.dependency_overrides[get_store] = lambda: tmp_store
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


def _wav_bytes() -> bytes:
    import struct

    header = b"RIFF" + struct.pack("<I", 36) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
    header += b"data" + struct.pack("<I", 0)
    return header


# ---------------------------------------------------------------------------
# 1. POST /api/telemost/join creates bot session
# ---------------------------------------------------------------------------


def test_join_creates_bot_session(client: TestClient) -> None:
    r = client.post(
        "/api/telemost/join",
        json={"meeting_url": "https://telemost.yandex.ru/j/demo123"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["bot_session_id"].startswith("bot_")
    assert body["status"] == "joining"
    assert body["message"] == "Telemost bot join requested"


# ---------------------------------------------------------------------------
# 2. meeting_id not provided → new meeting created
# ---------------------------------------------------------------------------


def test_join_auto_creates_meeting_id(client: TestClient) -> None:
    r = client.post(
        "/api/telemost/join",
        json={"meeting_url": "https://telemost.yandex.ru/j/no-id"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["meeting_id"]  # auto-generated UUID


# ---------------------------------------------------------------------------
# 3. meeting_id provided → used as-is
# ---------------------------------------------------------------------------


def test_join_uses_provided_meeting_id(client: TestClient) -> None:
    r = client.post(
        "/api/telemost/join",
        json={"meeting_url": "https://telemost.yandex.ru/j/abc", "meeting_id": "my-meeting"},
    )
    assert r.status_code == 200
    assert r.json()["meeting_id"] == "my-meeting"


# ---------------------------------------------------------------------------
# 4. GET /api/telemost/{bot_session_id}/status returns status
# ---------------------------------------------------------------------------


def test_get_status_returns_session(client: TestClient) -> None:
    join = client.post(
        "/api/telemost/join",
        json={"meeting_url": "https://telemost.yandex.ru/j/s1", "meeting_id": "m-status"},
    ).json()
    bot_id = join["bot_session_id"]

    r = client.get(f"/api/telemost/{bot_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["bot_session_id"] == bot_id
    assert body["meeting_id"] == "m-status"
    assert body["status"] == "joining"


# ---------------------------------------------------------------------------
# 5. POST /api/telemost/{bot_session_id}/leave → status "left"
# ---------------------------------------------------------------------------


def test_leave_sets_status_left(client: TestClient) -> None:
    join = client.post(
        "/api/telemost/join",
        json={"meeting_url": "https://telemost.yandex.ru/j/s2"},
    ).json()
    bot_id = join["bot_session_id"]

    r = client.post(f"/api/telemost/{bot_id}/leave")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "left"

    # Status endpoint should also show "left".
    r2 = client.get(f"/api/telemost/{bot_id}/status")
    assert r2.json()["status"] == "left"


# ---------------------------------------------------------------------------
# 6. Unknown bot_session_id → 404
# ---------------------------------------------------------------------------


def test_status_unknown_session_returns_404(client: TestClient) -> None:
    r = client.get("/api/telemost/nonexistent_bot/status")
    assert r.status_code == 404


def test_leave_unknown_session_returns_404(client: TestClient) -> None:
    r = client.post("/api/telemost/nonexistent_bot/leave")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 7. Invalid meeting_url → 400
# ---------------------------------------------------------------------------


def test_join_invalid_url_returns_400(client: TestClient) -> None:
    r = client.post(
        "/api/telemost/join",
        json={"meeting_url": "not-a-url"},
    )
    assert r.status_code == 400


def test_join_empty_url_returns_400(client: TestClient) -> None:
    r = client.post(
        "/api/telemost/join",
        json={"meeting_url": ""},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 8. Upload audio with source=telemost_bot is accepted
# ---------------------------------------------------------------------------


def test_upload_telemost_bot_source_accepted(client: TestClient) -> None:
    r = client.post(
        "/api/audio/upload",
        data={"agent_id": "bot-001", "source": "telemost_bot"},
        files={"audio": ("rec.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "uploaded"


# ---------------------------------------------------------------------------
# 9. Upload with unknown source → 400
# ---------------------------------------------------------------------------


def test_upload_unknown_source_returns_400(client: TestClient) -> None:
    r = client.post(
        "/api/audio/upload",
        data={"agent_id": "x", "source": "unknown_source"},
        files={"audio": ("rec.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 10. GET /api/meetings shows meetings with source telemost_bot
# ---------------------------------------------------------------------------


def test_meetings_list_shows_telemost_bot_source(client: TestClient) -> None:
    client.post(
        "/api/audio/upload",
        data={"agent_id": "bot-002", "meeting_id": "tele-meet", "source": "telemost_bot"},
        files={"audio": ("rec.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    r = client.get("/api/meetings")
    meetings = r.json()["meetings"]
    tele = next((m for m in meetings if m["meeting_id"] == "tele-meet"), None)
    assert tele is not None
    assert tele["source"] == "telemost_bot"
