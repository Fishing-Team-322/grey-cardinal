"""Tests for the YouGile board integration (mocked client — no real network).

Covers: config/status, confirm sync, move sync, manual re-sync, persistence.

Run:
    cd C:\\PythonProjekt\\grey-cardinal
    pytest apps/brain-api/tests/test_yougile_integration.py -v
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.routes.public_api import SimpleStore, get_store, set_store
from brain_api.api.routes.public_api import router as public_router
from brain_api.demo import routes as demo_routes
from brain_api.demo.store import BrainStore, get_brain_store, set_brain_store
from brain_api.integrations.yougile import (
    YouGileBoardService,
    YouGileConfig,
    YouGileHealth,
    YouGileHTTPError,
    get_yougile_service,
)

# --------------------------------------------------------------------------- #
# Fake YouGile client
# --------------------------------------------------------------------------- #


class FakeYouGileClient:
    def __init__(self, *, create_id="yg_1", fail_create=False, fail_move=False, health="connected"):
        self.created: list[dict] = []
        self.moved: list[dict] = []
        self._create_id = create_id
        self._fail_create = fail_create
        self._fail_move = fail_move
        self._health = health

    async def create_task(self, column_id, title, description="", assigned=None, metadata=None):
        if self._fail_create:
            raise YouGileHTTPError("POST", "/tasks", 500, "boom")
        self.created.append(
            {
                "column_id": column_id,
                "title": title,
                "description": description,
                "assigned": assigned,
            }
        )
        return {"id": self._create_id}

    async def move_task(self, task_id, column_id):
        if self._fail_move:
            raise YouGileHTTPError("PUT", f"/tasks/{task_id}", 500, "boom")
        self.moved.append({"task_id": task_id, "column_id": column_id})
        return {"id": task_id}

    async def get_columns(self, board_id):
        return [{"id": "col_todo"}, {"id": "col_inprog"}, {"id": "col_done"}]

    async def health_check(self):
        if self._health == "connected":
            return YouGileHealth(ok=True, status="connected")
        return YouGileHealth(ok=False, status="error", reason="bad creds")


def enabled_config(**overrides) -> YouGileConfig:
    base = {
        "enabled": True,
        "api_base": "https://ru.yougile.com",
        "api_key": "secret-key",
        "company_id": "co_1",
        "project_id": "proj_1",
        "board_id": "board_1",
        "column_todo_id": "col_todo",
        "column_in_progress_id": "col_inprog",
        "column_done_id": "col_done",
    }
    base.update(overrides)
    return YouGileConfig(**base)


def disabled_config() -> YouGileConfig:
    return YouGileConfig(enabled=False, api_base="https://ru.yougile.com", api_key="")


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


def build_client(brain_store, simple_store, service: YouGileBoardService) -> TestClient:
    app = FastAPI()
    app.include_router(public_router)
    app.include_router(demo_routes.router)
    app.dependency_overrides[get_brain_store] = lambda: brain_store
    app.dependency_overrides[get_store] = lambda: simple_store
    app.dependency_overrides[get_yougile_service] = lambda: service
    return TestClient(app)


def _make_proposal(client: TestClient) -> str:
    r = client.post(
        "/api/chat/messages",
        json={
            "chat_id": "demo",
            "author": "Денис",
            "text": "Нужно оплатить сервер до четверга, ответственный Иван",
        },
    )
    return r.json()["proposal"]["proposal_id"]


# =========================================================================== #
# Config / status
# =========================================================================== #


def test_config_disabled_when_env_missing() -> None:
    cfg = disabled_config()
    assert cfg.configured is False
    assert cfg.effective_enabled is False


def test_config_enabled_when_required_env_present() -> None:
    cfg = enabled_config()
    assert cfg.configured is True
    assert cfg.effective_enabled is True


def test_status_endpoint_disabled(brain_store, simple_store) -> None:
    client = build_client(brain_store, simple_store, YouGileBoardService(disabled_config()))
    r = client.get("/api/integrations/yougile/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["configured"] is False
    assert body["status"] == "disabled"
    assert body["reason"]


def test_status_endpoint_connected_with_mock(brain_store, simple_store) -> None:
    service = YouGileBoardService(enabled_config(), client=FakeYouGileClient())
    client = build_client(brain_store, simple_store, service)
    r = client.get("/api/integrations/yougile/status")
    body = r.json()
    assert body["enabled"] is True
    assert body["configured"] is True
    assert body["status"] == "connected"
    assert body["board_id"] == "board_1"


def test_columns_endpoint_returns_configured_ids(brain_store, simple_store) -> None:
    service = YouGileBoardService(enabled_config(), client=FakeYouGileClient())
    client = build_client(brain_store, simple_store, service)
    r = client.get("/api/integrations/yougile/columns")
    body = r.json()
    assert body["configured_columns"]["todo"] == "col_todo"
    assert body["verified"] is True
    assert body["columns_found"]["todo"] is True


# =========================================================================== #
# Confirm sync
# =========================================================================== #


def test_confirm_creates_local_task_when_disabled(brain_store, simple_store) -> None:
    client = build_client(brain_store, simple_store, YouGileBoardService(disabled_config()))
    pid = _make_proposal(client)
    task = client.post(f"/api/task-proposals/{pid}/confirm").json()["task"]
    assert task["status"] == "todo"
    assert task["yougile_status"] == "disabled"
    assert task["yougile_task_id"] == ""


def test_confirm_calls_create_task_when_enabled(brain_store, simple_store) -> None:
    fake = FakeYouGileClient()
    client = build_client(
        brain_store, simple_store, YouGileBoardService(enabled_config(), client=fake)
    )
    pid = _make_proposal(client)
    task = client.post(f"/api/task-proposals/{pid}/confirm").json()["task"]
    assert len(fake.created) == 1
    assert fake.created[0]["column_id"] == "col_todo"
    assert task["yougile_status"] == "synced"


def test_confirm_saves_yougile_task_id(brain_store, simple_store) -> None:
    fake = FakeYouGileClient(create_id="yg_777")
    client = build_client(
        brain_store, simple_store, YouGileBoardService(enabled_config(), client=fake)
    )
    pid = _make_proposal(client)
    task = client.post(f"/api/task-proposals/{pid}/confirm").json()["task"]
    assert task["yougile_task_id"] == "yg_777"


def test_confirm_create_error_sets_error_status_keeps_local_task(brain_store, simple_store) -> None:
    fake = FakeYouGileClient(fail_create=True)
    client = build_client(
        brain_store, simple_store, YouGileBoardService(enabled_config(), client=fake)
    )
    pid = _make_proposal(client)
    task = client.post(f"/api/task-proposals/{pid}/confirm").json()["task"]
    assert task["yougile_status"] == "error"
    assert task["yougile_error"]
    # Local task still exists on the board.
    tasks = client.get("/api/tasks").json()["tasks"]
    assert len(tasks) == 1


def test_yougile_description_contains_metadata(brain_store, simple_store) -> None:
    fake = FakeYouGileClient()
    client = build_client(
        brain_store, simple_store, YouGileBoardService(enabled_config(), client=fake)
    )
    pid = _make_proposal(client)
    client.post(f"/api/task-proposals/{pid}/confirm")
    desc = fake.created[0]["description"]
    assert "Source: chat" in desc
    assert "Proposal:" in desc
    assert "Confidence:" in desc
    assert "Deadline:" in desc
    assert "Grey Cardinal" in desc


def test_yougile_assignee_mapped_to_user_id(brain_store, simple_store) -> None:
    fake = FakeYouGileClient()
    cfg = enabled_config(user_map={"Иван": "user_id_1"})
    client = build_client(brain_store, simple_store, YouGileBoardService(cfg, client=fake))
    pid = _make_proposal(client)
    client.post(f"/api/task-proposals/{pid}/confirm")
    assert fake.created[0]["assigned"] == ["user_id_1"]


# =========================================================================== #
# Move sync
# =========================================================================== #


def _confirm_synced_task(client: TestClient) -> str:
    pid = _make_proposal(client)
    return client.post(f"/api/task-proposals/{pid}/confirm").json()["task"]["task_id"]


def test_move_calls_yougile_move(brain_store, simple_store) -> None:
    fake = FakeYouGileClient()
    client = build_client(
        brain_store, simple_store, YouGileBoardService(enabled_config(), client=fake)
    )
    task_id = _confirm_synced_task(client)
    r = client.post(f"/api/tasks/{task_id}/move", json={"status": "in_progress"})
    assert r.status_code == 200
    assert fake.moved[-1]["column_id"] == "col_inprog"
    assert r.json()["task"]["yougile_status"] == "synced"


def test_move_invalid_status_400(brain_store, simple_store) -> None:
    fake = FakeYouGileClient()
    client = build_client(
        brain_store, simple_store, YouGileBoardService(enabled_config(), client=fake)
    )
    task_id = _confirm_synced_task(client)
    r = client.post(f"/api/tasks/{task_id}/move", json={"status": "archived"})
    assert r.status_code == 400


def test_move_yougile_error_sets_error_status(brain_store, simple_store) -> None:
    fake = FakeYouGileClient(fail_move=True)
    client = build_client(
        brain_store, simple_store, YouGileBoardService(enabled_config(), client=fake)
    )
    task_id = _confirm_synced_task(client)
    r = client.post(f"/api/tasks/{task_id}/move", json={"status": "done"})
    assert r.status_code == 200
    # Local move stands; YouGile sync flagged as error.
    assert r.json()["task"]["status"] == "done"
    assert r.json()["task"]["yougile_status"] == "error"


def test_sync_retry_endpoint_retries_failed_task(brain_store, simple_store) -> None:
    # First confirm fails to create in YouGile.
    fail = FakeYouGileClient(fail_create=True)
    service = YouGileBoardService(enabled_config(), client=fail)
    client = build_client(brain_store, simple_store, service)
    pid = _make_proposal(client)
    task = client.post(f"/api/task-proposals/{pid}/confirm").json()["task"]
    assert task["yougile_status"] == "error"
    task_id = task["task_id"]

    # Now the client recovers; retry should create the task.
    service._client = FakeYouGileClient(create_id="yg_recovered")  # noqa: SLF001
    r = client.post(f"/api/tasks/{task_id}/sync-yougile")
    assert r.status_code == 200
    assert r.json()["task"]["yougile_status"] == "synced"
    assert r.json()["task"]["yougile_task_id"] == "yg_recovered"


def test_sync_retry_unknown_task_404(brain_store, simple_store) -> None:
    service = YouGileBoardService(enabled_config(), client=FakeYouGileClient())
    client = build_client(brain_store, simple_store, service)
    r = client.post("/api/tasks/task_nope/sync-yougile")
    assert r.status_code == 404


# =========================================================================== #
# Persistence
# =========================================================================== #


def test_yougile_task_id_persists_after_reload(tmp_path) -> None:
    base = tmp_path / "brain"
    store1 = BrainStore(base)
    proposal = store1.create_proposal({"title": "T", "assignee": "Иван", "deadline": "завтра"})
    task = store1.create_task_from_proposal(proposal)
    store1.update_task_yougile(
        task["task_id"], yougile_status="synced", yougile_task_id="yg_persist"
    )

    store2 = BrainStore(base)
    reloaded = store2.get_task(task["task_id"])
    assert reloaded is not None
    assert reloaded["yougile_task_id"] == "yg_persist"
    assert reloaded["yougile_status"] == "synced"


def test_tasks_and_proposals_persist_after_restart(tmp_path) -> None:
    base = tmp_path / "brain"
    store1 = BrainStore(base)
    p = store1.create_proposal({"title": "Persist me", "assignee": "Маша", "deadline": "пятница"})
    store1.create_task_from_proposal(p)

    store2 = BrainStore(base)
    assert len(store2.list_proposals()) == 1
    assert len(store2.list_tasks()) == 1


def test_corrupted_json_creates_backup_and_starts(tmp_path) -> None:
    base = tmp_path / "brain"
    base.mkdir(parents=True)
    corrupt = base / "brain.json"
    corrupt.write_text("{ this is not valid json", encoding="utf-8")

    # Should not raise; starts with empty state.
    store = BrainStore(base)
    assert store.list_tasks() == []

    backups = list(base.glob("brain.json.corrupt-*.bak"))
    assert len(backups) == 1
    assert "not valid json" in backups[0].read_text(encoding="utf-8")


def test_brain_store_path_round_trip(tmp_path) -> None:
    """Atomic write produces valid, reloadable JSON at the configured path."""
    base = tmp_path / "data"
    store = BrainStore(base, "brain.json")
    store.create_proposal({"title": "X", "assignee": "Иван", "deadline": "завтра"})
    on_disk = json.loads((base / "brain.json").read_text(encoding="utf-8"))
    assert "proposals" in on_disk and len(on_disk["proposals"]) == 1
