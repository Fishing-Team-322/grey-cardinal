"""Tests for account/workspace pairing + daemon agent ownership.

Covers: profile, one-time/expiring pairing codes, agent registration + token,
heartbeat auth, upload ownership, workspace isolation, transcript→proposal.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.routes.agents import router as agents_router
from brain_api.demo import routes as demo_routes
from brain_api.demo.agents import AgentsStore, get_agents_store
from brain_api.demo.store import BrainStore, get_brain_store


@pytest.fixture
def agents_store(tmp_path) -> AgentsStore:
    return AgentsStore(tmp_path / "agents")


@pytest.fixture
def brain_store(tmp_path) -> BrainStore:
    return BrainStore(tmp_path / "brain")


@pytest.fixture
def client(agents_store: AgentsStore, brain_store: BrainStore) -> TestClient:
    app = FastAPI()
    app.include_router(agents_router)
    app.include_router(demo_routes.router)
    app.dependency_overrides[get_agents_store] = lambda: agents_store
    app.dependency_overrides[get_brain_store] = lambda: brain_store
    return TestClient(app)


def _pair_and_register(client: TestClient, device="Denis laptop") -> dict:
    code = client.post("/api/agents/pairing-code").json()["pairing_code"]
    r = client.post(
        "/api/agents/register",
        json={
            "pairing_code": code,
            "device_name": device,
            "os": "windows",
            "daemon_version": "0.4.0",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_profile_has_account_number(client: TestClient) -> None:
    r = client.get("/api/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["account_number"].startswith("GC-")
    assert body["workspace_id"]
    assert body["account_id"]


def test_pairing_code_is_one_time(client: TestClient) -> None:
    code = client.post("/api/agents/pairing-code").json()["pairing_code"]
    first = client.post("/api/agents/register", json={"pairing_code": code, "device_name": "A"})
    assert first.status_code == 200
    second = client.post("/api/agents/register", json={"pairing_code": code, "device_name": "B"})
    assert second.status_code == 400  # already used


def test_register_returns_token_and_binds_workspace(client: TestClient) -> None:
    profile_ws = client.get("/api/profile").json()["workspace_id"]
    reg = _pair_and_register(client)
    assert reg["agent_token"].startswith("gca_")
    assert reg["workspace_id"] == profile_ws
    assert reg["agent_id"].startswith("agent_")


def test_invalid_pairing_code_rejected(client: TestClient) -> None:
    r = client.post("/api/agents/register", json={"pairing_code": "GC-000000", "device_name": "X"})
    assert r.status_code == 400


def test_heartbeat_requires_token_and_updates_status(client: TestClient) -> None:
    reg = _pair_and_register(client)
    # No token → 401.
    assert client.post("/api/agents/heartbeat", json={"status": "idle"}).status_code == 401
    # With token → ok, status reflected in listing.
    hb = client.post(
        "/api/agents/heartbeat",
        json={"status": "recording", "version": "0.4.0"},
        headers={"X-Agent-Token": reg["agent_token"]},
    )
    assert hb.status_code == 200
    assert hb.json()["agent"]["recording_status"] == "recording"
    listed = client.get("/api/agents").json()["agents"]
    assert any(a["agent_id"] == reg["agent_id"] and a["online"] for a in listed)


def test_upload_is_owned_by_workspace_and_creates_proposal(client: TestClient) -> None:
    reg = _pair_and_register(client)
    r = client.post(
        "/api/daemon/uploads",
        data={
            "recording_id": "rec-1",
            "duration_sec": "12",
            "source": "microphone",
            "transcript_text": "Максим, сделай сайт до пятницы",
        },
        files={"audio": ("rec.wav", b"RIFFxxxx", "audio/wav")},
        headers={"X-Agent-Token": reg["agent_token"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workspace_id"] == reg["workspace_id"]
    assert body["agent_id"] == reg["agent_id"]
    assert body["proposal_created"] is True

    uploads = client.get("/api/daemon/uploads").json()["uploads"]
    assert len(uploads) == 1
    assert uploads[0]["agent_id"] == reg["agent_id"]

    # The proposal is visible in the demo board pipeline.
    proposals = client.get("/api/task-proposals").json()["proposals"]
    assert any("сайт" in p["title"].lower() for p in proposals)


def test_upload_without_token_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/daemon/uploads",
        data={"recording_id": "x"},
        headers={"X-Agent-Token": "gca_wrong"},
    )
    assert r.status_code == 401


def test_workspace_isolation(client: TestClient, agents_store: AgentsStore) -> None:
    # Workspace 1 (default): one agent + one upload.
    reg1 = _pair_and_register(client, device="WS1 device")
    client.post(
        "/api/daemon/uploads",
        data={"recording_id": "r1"},
        headers={"X-Agent-Token": reg1["agent_token"]},
    )
    ws1_id = reg1["workspace_id"]

    # Inject a real second workspace and pair an agent into it.
    agents_store._workspaces["ws_two"] = {
        "workspace_id": "ws_two",
        "account_id": "acc_two",
        "account_number": "GC-TWOABC",
        "display_name": "WS2",
        "is_default": False,
        "created_at": "2026-01-01T00:00:00Z",
    }
    code2 = agents_store.create_pairing_code("ws_two")["pairing_code"]
    reg2 = client.post(
        "/api/agents/register", json={"pairing_code": code2, "device_name": "WS2 device"}
    ).json()
    assert reg2["workspace_id"] == "ws_two"
    client.post(
        "/api/daemon/uploads",
        data={"recording_id": "r2"},
        headers={"X-Agent-Token": reg2["agent_token"]},
    )

    # Each workspace sees only its own agents/uploads.
    a1 = client.get(f"/api/agents?workspace_id={ws1_id}").json()["agents"]
    a2 = client.get("/api/agents?workspace_id=ws_two").json()["agents"]
    assert {a["agent_id"] for a in a1} == {reg1["agent_id"]}
    assert {a["agent_id"] for a in a2} == {reg2["agent_id"]}

    u1 = client.get(f"/api/daemon/uploads?workspace_id={ws1_id}").json()["uploads"]
    u2 = client.get("/api/daemon/uploads?workspace_id=ws_two").json()["uploads"]
    assert len(u1) == 1 and u1[0]["workspace_id"] == ws1_id
    assert len(u2) == 1 and u2[0]["workspace_id"] == "ws_two"


def test_unpair_removes_agent(client: TestClient) -> None:
    reg = _pair_and_register(client)
    assert len(client.get("/api/agents").json()["agents"]) == 1
    r = client.post(f"/api/agents/{reg['agent_id']}/unpair")
    assert r.status_code == 200
    assert len(client.get("/api/agents").json()["agents"]) == 0
    # Token no longer valid after unpair.
    assert (
        client.post(
            "/api/agents/heartbeat",
            json={"status": "idle"},
            headers={"X-Agent-Token": reg["agent_token"]},
        ).status_code
        == 401
    )
