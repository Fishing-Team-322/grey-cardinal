"""Tests for Telemost bot endpoints and audio upload source validation.

14 test scenarios required:
 1. POST /api/telemost/join creates bot session
 2. join without meeting_id auto-creates meeting
 3. join with meeting_id uses it
 4. after join, meeting appears in GET /api/meetings
 5. meeting after join has source=telemost_bot
 6. invalid meeting_url → 400
 7. GET /api/telemost/{id}/status returns status
 8. POST /api/telemost/{id}/leave → status "left"
 9. unknown bot_session_id → 404
10. POST /api/audio/upload with source=telemost_bot accepted
11. upload with source=telemost_bot shows meeting status "uploaded" in meetings list
12. upload with unknown source → 400
13. GET /api/meetings/{id} shows audios after upload
14. GET /api/meetings/{id}/tasks returns empty list (no fake tasks)

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
from brain_api.telemost_worker.factory import reset_worker

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_state():
    """Isolate bot sessions and worker singleton between tests."""
    session_manager.clear_all()
    reset_worker()
    yield
    session_manager.clear_all()
    reset_worker()


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


def _join(
    client: TestClient, url: str = "https://telemost.yandex.ru/j/demo", meeting_id: str = ""
) -> dict:
    payload = {"meeting_url": url}
    if meeting_id:
        payload["meeting_id"] = meeting_id
    r = client.post("/api/telemost/join", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# 1. POST /api/telemost/join creates bot session
# ---------------------------------------------------------------------------


def test_join_creates_bot_session(client: TestClient) -> None:
    body = _join(client)
    assert body["ok"] is True
    assert body["bot_session_id"].startswith("bot_")
    assert body["status"] == "joining"
    assert body["message"] == "Telemost bot join requested"


# ---------------------------------------------------------------------------
# 2. join without meeting_id auto-creates meeting
# ---------------------------------------------------------------------------


def test_join_auto_creates_meeting_id(client: TestClient) -> None:
    body = _join(client)
    mid = body["meeting_id"]
    assert mid  # auto-generated UUID, not empty


# ---------------------------------------------------------------------------
# 3. join with meeting_id uses it
# ---------------------------------------------------------------------------


def test_join_uses_provided_meeting_id(client: TestClient) -> None:
    body = _join(client, meeting_id="my-explicit-meeting")
    assert body["meeting_id"] == "my-explicit-meeting"


# ---------------------------------------------------------------------------
# 4. after join, meeting appears in GET /api/meetings
# ---------------------------------------------------------------------------


def test_join_meeting_visible_in_list(client: TestClient) -> None:
    _join(client, meeting_id="visible-meeting")
    r = client.get("/api/meetings")
    assert r.status_code == 200
    ids = [m["meeting_id"] for m in r.json()["meetings"]]
    assert "visible-meeting" in ids


# ---------------------------------------------------------------------------
# 5. meeting after join has source=telemost_bot
# ---------------------------------------------------------------------------


def test_join_meeting_has_telemost_bot_source(client: TestClient) -> None:
    _join(client, meeting_id="source-check")
    r = client.get("/api/meetings")
    meetings = r.json()["meetings"]
    meeting = next(m for m in meetings if m["meeting_id"] == "source-check")
    assert meeting["source"] == "telemost_bot"


# ---------------------------------------------------------------------------
# 6. invalid meeting_url → 400
# ---------------------------------------------------------------------------


def test_join_invalid_url_returns_400(client: TestClient) -> None:
    r = client.post("/api/telemost/join", json={"meeting_url": "not-a-url"})
    assert r.status_code == 400


def test_join_empty_url_returns_400(client: TestClient) -> None:
    r = client.post("/api/telemost/join", json={"meeting_url": ""})
    assert r.status_code == 400


def test_join_http_url_returns_400(client: TestClient) -> None:
    r = client.post(
        "/api/telemost/join", json={"meeting_url": "http://telemost.yandex.ru/j/insecure"}
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 7. GET /api/telemost/{id}/status returns status
# ---------------------------------------------------------------------------


def test_get_status_returns_joining(client: TestClient) -> None:
    body = _join(client, meeting_id="status-test")
    bot_id = body["bot_session_id"]

    r = client.get(f"/api/telemost/{bot_id}/status")
    assert r.status_code == 200
    s = r.json()
    assert s["ok"] is True
    assert s["bot_session_id"] == bot_id
    assert s["meeting_id"] == "status-test"
    assert s["status"] == "joining"


# ---------------------------------------------------------------------------
# 8. POST /api/telemost/{id}/leave → status "left"
# ---------------------------------------------------------------------------


def test_leave_sets_status_left(client: TestClient) -> None:
    body = _join(client, meeting_id="leave-test")
    bot_id = body["bot_session_id"]

    r = client.post(f"/api/telemost/{bot_id}/leave")
    assert r.status_code == 200
    s = r.json()
    assert s["ok"] is True
    assert s["status"] == "left"

    # Verify via status endpoint.
    r2 = client.get(f"/api/telemost/{bot_id}/status")
    assert r2.json()["status"] == "left"


# ---------------------------------------------------------------------------
# 9. unknown bot_session_id → 404
# ---------------------------------------------------------------------------


def test_status_unknown_session_returns_404(client: TestClient) -> None:
    r = client.get("/api/telemost/nonexistent_bot_xyz/status")
    assert r.status_code == 404


def test_leave_unknown_session_returns_404(client: TestClient) -> None:
    r = client.post("/api/telemost/nonexistent_bot_xyz/leave")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 10. POST /api/audio/upload with source=telemost_bot accepted
# ---------------------------------------------------------------------------


def test_upload_telemost_bot_source_accepted(client: TestClient) -> None:
    r = client.post(
        "/api/audio/upload",
        data={"agent_id": "bot-001", "source": "telemost_bot", "meeting_id": "tele-upload"},
        files={"audio": ("rec.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "uploaded"


# ---------------------------------------------------------------------------
# 11. upload with source=telemost_bot → meeting status "uploaded" in list
# ---------------------------------------------------------------------------


def test_upload_telemost_bot_meeting_status_uploaded(client: TestClient) -> None:
    mid = "tele-status-upload"
    client.post(
        "/api/audio/upload",
        data={"agent_id": "bot-002", "source": "telemost_bot", "meeting_id": mid},
        files={"audio": ("rec.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    r = client.get("/api/meetings")
    meeting = next(m for m in r.json()["meetings"] if m["meeting_id"] == mid)
    assert meeting["status"] == "uploaded"
    assert meeting["source"] == "telemost_bot"


# ---------------------------------------------------------------------------
# 12. upload with unknown source → 400
# ---------------------------------------------------------------------------


def test_upload_unknown_source_returns_400(client: TestClient) -> None:
    r = client.post(
        "/api/audio/upload",
        data={"agent_id": "x", "source": "alien_source"},
        files={"audio": ("rec.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 13. GET /api/meetings/{id} shows audios after upload
# ---------------------------------------------------------------------------


def test_meeting_detail_shows_audios_after_upload(client: TestClient) -> None:
    mid = "tele-detail-audios"
    client.post(
        "/api/audio/upload",
        data={"agent_id": "bot-003", "source": "telemost_bot", "meeting_id": mid},
        files={"audio": ("rec.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
    )
    r = client.get(f"/api/meetings/{mid}")
    assert r.status_code == 200
    detail = r.json()["meeting"]
    assert detail["meeting_id"] == mid
    assert len(detail["audios"]) == 1
    assert detail["audios"][0]["status"] == "uploaded"


# ---------------------------------------------------------------------------
# 14. GET /api/meetings/{id}/tasks returns empty list (no fake tasks)
# ---------------------------------------------------------------------------


def test_meeting_tasks_empty_no_fake_tasks(client: TestClient) -> None:
    _join(client, meeting_id="tele-tasks-empty")
    r = client.get("/api/meetings/tele-tasks-empty/tasks")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["tasks"] == []
