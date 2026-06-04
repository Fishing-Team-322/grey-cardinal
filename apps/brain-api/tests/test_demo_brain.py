"""Tests for the autonomous demo brain pipeline.

Covers: chat extraction, proposals, confirm/reject, board, move, digest,
transcript (unavailable + manual injection) and the rule-based extractor.

Run:
    cd C:\\PythonProjekt\\grey-cardinal
    pytest apps/brain-api/tests/test_demo_brain.py -v
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.routes.public_api import SimpleStore, get_store, set_store
from brain_api.api.routes.public_api import router as public_router
from brain_api.demo import routes as demo_routes
from brain_api.demo.extractor import extract_task
from brain_api.demo.store import BrainStore, get_brain_store, set_brain_store
from brain_api.integrations.yougile import YouGileBoardService, YouGileConfig, get_yougile_service

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def brain_store(tmp_path) -> BrainStore:
    store = BrainStore(tmp_path / "brain")
    set_brain_store(store)
    return store


@pytest.fixture
def simple_store(tmp_path) -> SimpleStore:
    store = SimpleStore(tmp_path / "uploads")
    set_store(store)
    return store


@pytest.fixture
def app(brain_store: BrainStore, simple_store: SimpleStore) -> FastAPI:
    application = FastAPI()
    application.include_router(public_router)
    application.include_router(demo_routes.router)
    application.dependency_overrides[get_brain_store] = lambda: brain_store
    application.dependency_overrides[get_store] = lambda: simple_store
    # Hermetic: YouGile disabled so confirm/move never touch the network.
    disabled = YouGileBoardService(
        YouGileConfig(enabled=False, api_base="https://ru.yougile.com", api_key="")
    )
    application.dependency_overrides[get_yougile_service] = lambda: disabled
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _send(client: TestClient, text: str, author: str = "Денис", message_id: str = "") -> dict:
    r = client.post(
        "/api/chat/messages",
        json={"chat_id": "demo", "message_id": message_id, "author": author, "text": text},
    )
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Extractor unit tests (the 5 required examples)
# --------------------------------------------------------------------------- #


def test_extractor_pay_server() -> None:
    e = extract_task("Нужно оплатить сервер до четверга, ответственный Иван", author="Денис")
    assert e.has_task is True
    assert "сервер" in e.title.lower()
    assert e.assignee == "Иван"
    assert "четверг" in e.deadline.lower()


def test_extractor_landing() -> None:
    e = extract_task("Денис, сделай лендинг завтра", author="Аноним")
    assert e.has_task is True
    assert "лендинг" in e.title.lower()
    assert e.assignee == "Денис"
    assert e.deadline.lower() == "завтра"


def test_extractor_report() -> None:
    e = extract_task("Маша подготовит отчёт к пятнице", author="Денис")
    assert e.has_task is True
    assert "отчёт" in e.title.lower()
    assert e.assignee == "Маша"
    assert "пятниц" in e.deadline.lower()


def test_extractor_readme_fallback_author() -> None:
    e = extract_task("надо обновить README сегодня", author="Денис")
    assert e.has_task is True
    assert "readme" in e.title.lower()
    assert e.assignee == "Денис"  # fallback to author
    assert e.deadline.lower() == "сегодня"


def test_extractor_assign_petya() -> None:
    e = extract_task("поставь задачу Пете проверить API до вечера", author="Денис")
    assert e.has_task is True
    assert "api" in e.title.lower()
    assert e.assignee == "Пете"
    assert "вечер" in e.deadline.lower()


def test_extractor_no_task() -> None:
    e = extract_task("Всем привет, как дела?", author="Денис")
    assert e.has_task is False


# --------------------------------------------------------------------------- #
# Chat → proposal
# --------------------------------------------------------------------------- #


def test_message_without_task(client: TestClient) -> None:
    body = _send(client, "Спасибо за встречу, отличный день")
    assert body["has_task"] is False
    assert body["proposal"] is None


def test_message_with_task_creates_pending_proposal(client: TestClient) -> None:
    body = _send(client, "Нужно оплатить сервер до четверга, ответственный Иван")
    assert body["has_task"] is True
    assert body["proposal"]["status"] == "pending"


def test_proposal_extracts_title(client: TestClient) -> None:
    body = _send(client, "Нужно оплатить сервер до четверга, ответственный Иван")
    assert "сервер" in body["proposal"]["title"].lower()


def test_proposal_extracts_assignee(client: TestClient) -> None:
    body = _send(client, "Нужно оплатить сервер до четверга, ответственный Иван")
    assert body["proposal"]["assignee"] == "Иван"


def test_proposal_extracts_deadline(client: TestClient) -> None:
    body = _send(client, "Денис, сделай лендинг завтра")
    assert body["proposal"]["deadline"].lower() == "завтра"


def test_duplicate_message_no_second_proposal(client: TestClient) -> None:
    first = _send(client, "Нужно оплатить сервер до четверга, ответственный Иван", message_id="m1")
    second = _send(client, "Нужно оплатить сервер до четверга, ответственный Иван", message_id="m2")
    assert first["has_task"] is True
    assert second.get("duplicate") is True
    assert second["existing_proposal_id"] == first["proposal"]["proposal_id"]

    r = client.get("/api/task-proposals?status=pending")
    assert len(r.json()["proposals"]) == 1


def test_duplicate_after_confirm_still_deduped(client: TestClient) -> None:
    first = _send(client, "Денис, сделай лендинг завтра", message_id="m1")
    pid = first["proposal"]["proposal_id"]
    client.post(f"/api/task-proposals/{pid}/confirm")
    # Re-sending the same task after confirming must not create a new proposal.
    second = _send(client, "Денис, сделай лендинг завтра", message_id="m2")
    assert second.get("duplicate") is True
    assert second["existing_proposal_id"] == pid


# --------------------------------------------------------------------------- #
# Proposals: list / confirm / reject
# --------------------------------------------------------------------------- #


def test_list_proposals(client: TestClient) -> None:
    _send(client, "надо обновить README сегодня")
    r = client.get("/api/task-proposals")
    assert r.status_code == 200
    assert len(r.json()["proposals"]) >= 1


def test_confirm_proposal_creates_task(client: TestClient) -> None:
    body = _send(client, "Нужно оплатить сервер до четверга, ответственный Иван")
    pid = body["proposal"]["proposal_id"]
    r = client.post(f"/api/task-proposals/{pid}/confirm")
    assert r.status_code == 200
    data = r.json()
    assert data["task"]["task_id"].startswith("task_")
    assert data["task"]["status"] == "todo"

    # Proposal now confirmed.
    plist = client.get("/api/task-proposals?status=confirmed").json()["proposals"]
    assert any(p["proposal_id"] == pid for p in plist)


def test_reject_proposal_no_task(client: TestClient) -> None:
    body = _send(client, "надо обновить README сегодня")
    pid = body["proposal"]["proposal_id"]
    r = client.post(f"/api/task-proposals/{pid}/reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    # No tasks created.
    tasks = client.get("/api/tasks").json()["tasks"]
    assert tasks == []


def test_confirm_unknown_proposal_404(client: TestClient) -> None:
    r = client.post("/api/task-proposals/proposal_doesnotexist/confirm")
    assert r.status_code == 404


def test_reject_unknown_proposal_404(client: TestClient) -> None:
    r = client.post("/api/task-proposals/proposal_doesnotexist/reject")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Board
# --------------------------------------------------------------------------- #


def test_board_returns_columns(client: TestClient) -> None:
    r = client.get("/api/board")
    assert r.status_code == 200
    cols = r.json()["columns"]
    ids = [c["id"] for c in cols]
    assert ids == ["todo", "in_progress", "done"]


def test_confirmed_task_appears_in_todo(client: TestClient) -> None:
    body = _send(client, "Нужно оплатить сервер до четверга, ответственный Иван")
    pid = body["proposal"]["proposal_id"]
    client.post(f"/api/task-proposals/{pid}/confirm")

    board = client.get("/api/board").json()
    todo = next(c for c in board["columns"] if c["id"] == "todo")
    assert len(todo["tasks"]) == 1
    assert "сервер" in todo["tasks"][0]["title"].lower()


def _confirm_one(client: TestClient) -> str:
    body = _send(client, "Нужно оплатить сервер до четверга, ответственный Иван")
    pid = body["proposal"]["proposal_id"]
    task = client.post(f"/api/task-proposals/{pid}/confirm").json()["task"]
    return task["task_id"]


def test_move_task_to_in_progress(client: TestClient) -> None:
    task_id = _confirm_one(client)
    r = client.post(f"/api/tasks/{task_id}/move", json={"status": "in_progress"})
    assert r.status_code == 200
    assert r.json()["task"]["status"] == "in_progress"

    board = client.get("/api/board").json()
    in_prog = next(c for c in board["columns"] if c["id"] == "in_progress")
    assert len(in_prog["tasks"]) == 1


def test_move_task_to_done(client: TestClient) -> None:
    task_id = _confirm_one(client)
    r = client.post(f"/api/tasks/{task_id}/move", json={"status": "done"})
    assert r.status_code == 200
    assert r.json()["task"]["status"] == "done"


def test_move_invalid_status_400(client: TestClient) -> None:
    task_id = _confirm_one(client)
    r = client.post(f"/api/tasks/{task_id}/move", json={"status": "archived"})
    assert r.status_code == 400


def test_move_unknown_task_404(client: TestClient) -> None:
    r = client.post("/api/tasks/task_nope/move", json={"status": "done"})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Digest
# --------------------------------------------------------------------------- #


def test_digest_returns_pending_proposals(client: TestClient) -> None:
    _send(client, "надо обновить README сегодня")
    r = client.get("/api/digest/evening")
    assert r.status_code == 200
    data = r.json()
    assert len(data["pending_proposals"]) >= 1


def test_digest_includes_tasks_by_assignee(client: TestClient) -> None:
    body = _send(client, "Нужно оплатить сервер до четверга, ответственный Иван")
    pid = body["proposal"]["proposal_id"]
    client.post(f"/api/task-proposals/{pid}/confirm")

    data = client.get("/api/digest/evening").json()
    assert "Иван" in data["by_assignee"]
    assert any("сервер" in title.lower() for title in data["by_assignee"]["Иван"])


# --------------------------------------------------------------------------- #
# Transcript
# --------------------------------------------------------------------------- #


def test_transcript_unavailable_without_stt(client: TestClient) -> None:
    r = client.get("/api/meetings/no-transcript-meeting/transcript")
    assert r.status_code == 200
    data = r.json()
    assert data["transcription_status"] == "unavailable"
    assert "STT" in data["reason"]


def test_post_manual_transcript_creates_proposal(client: TestClient) -> None:
    r = client.post(
        "/api/meetings/demo-meeting/transcript",
        json={"text": "Нужно оплатить сервер до четверга, ответственный Иван", "speaker": "Денис"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["has_task"] is True
    assert data["proposal"]["source"] == "meeting_transcript"

    # Transcript now available.
    t = client.get("/api/meetings/demo-meeting/transcript").json()
    assert t["transcription_status"] == "available"
    assert len(t["lines"]) == 1


def test_transcript_proposal_can_be_confirmed(client: TestClient) -> None:
    data = client.post(
        "/api/meetings/m-confirm/transcript",
        json={"text": "Маша подготовит отчёт к пятнице", "speaker": "Денис"},
    ).json()
    pid = data["proposal"]["proposal_id"]
    r = client.post(f"/api/task-proposals/{pid}/confirm")
    assert r.status_code == 200
    assert r.json()["task"]["status"] == "todo"


def test_post_transcript_meeting_appears_in_meetings(client: TestClient) -> None:
    client.post(
        "/api/meetings/tele-from-transcript/transcript",
        json={"text": "надо обновить README сегодня", "speaker": "Денис"},
    )
    meetings = client.get("/api/meetings").json()["meetings"]
    m = next((x for x in meetings if x["meeting_id"] == "tele-from-transcript"), None)
    assert m is not None
    assert m["source"] == "telemost_bot"
