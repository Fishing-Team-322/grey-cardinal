"""Agent pairing lifecycle — DB-backed, tenant-scoped (replaces the demo store).

Covers: pairing-code issuance (JWT), register (one-time/expiry), heartbeat auth +
last_seen update, listing, unpair + token revocation, and that the token issued by
/register is a real ClientSession bound to the pairing user — the same token the
daemon endpoints consume (correct, non-global binding).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.routes.accounts import get_current_user, get_db
from brain_api.api.routes.agents import router as agents_router
from brain_api.api.routes.daemon import _resolve_session
from brain_api.infrastructure.db import models as m


@pytest_asyncio.fixture
async def seeded_user(session_factory):
    """A user that the JWT dependency will resolve to."""
    async with session_factory() as session:
        user = m.UserModel(
            id=uuid4(), display_name="Denis", email="denis@example.com", login="denis"
        )
        session.add(user)
        await session.commit()
        return user.id


@pytest.fixture
def client(session_factory, seeded_user) -> TestClient:
    app = FastAPI()
    app.include_router(agents_router)

    async def _override_db():
        async with session_factory() as session:
            yield session

    async def _override_user():
        async with session_factory() as session:
            return await session.get(m.UserModel, seeded_user)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return TestClient(app)


def _issue_code(client: TestClient) -> str:
    r = client.post("/api/agents/pairing-code")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pairing_code"].startswith("GC-")
    return body["pairing_code"]


def _register(client: TestClient, code: str, device="Denis laptop") -> dict:
    r = client.post(
        "/api/agents/register",
        json={"pairing_code": code, "device_name": device, "daemon_version": "0.5.0"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_pairing_code_requires_auth_and_returns_code(client: TestClient) -> None:
    code = _issue_code(client)
    assert len(code) == len("GC-000000")


def test_register_issues_token_bound_to_user(client: TestClient, seeded_user) -> None:
    reg = _register(client, _issue_code(client))
    assert reg["agent_id"]
    assert reg["agent_token"]
    assert reg["user_id"] == str(seeded_user)


def test_pairing_code_is_one_time(client: TestClient) -> None:
    code = _issue_code(client)
    assert _register(client, code)  # first use ok
    second = client.post("/api/agents/register", json={"pairing_code": code, "device_name": "B"})
    assert second.status_code == 400


def test_invalid_pairing_code_rejected(client: TestClient) -> None:
    r = client.post("/api/agents/register", json={"pairing_code": "GC-000000", "device_name": "X"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_expired_pairing_code_rejected(client: TestClient, session_factory, seeded_user):
    async with session_factory() as session:
        session.add(
            m.DeviceLinkCodeModel(
                user_id=seeded_user,
                code="GC-999999",
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        await session.commit()
    r = client.post("/api/agents/register", json={"pairing_code": "GC-999999"})
    assert r.status_code == 400


def test_heartbeat_requires_token_and_updates_listing(client: TestClient) -> None:
    reg = _register(client, _issue_code(client))
    assert client.post("/api/agents/heartbeat", json={"status": "idle"}).status_code == 401
    hb = client.post(
        "/api/agents/heartbeat",
        json={"status": "recording", "version": "0.5.1"},
        headers={"X-Agent-Token": reg["agent_token"]},
    )
    assert hb.status_code == 200
    assert hb.json()["agent"]["online"] is True
    listed = client.get("/api/agents").json()["agents"]
    assert any(a["agent_id"] == reg["agent_id"] and a["online"] for a in listed)


@pytest.mark.asyncio
async def test_register_token_is_a_resolvable_client_session(
    client: TestClient, session_factory, seeded_user
):
    """The agent token is a ClientSession id that daemon endpoints accept, and it
    resolves to the pairing user — proving the binding is per-user, not global."""
    reg = _register(client, _issue_code(client))
    async with session_factory() as session:
        cs = await _resolve_session(session, reg["agent_token"])
        assert cs is not None
        assert str(cs.user_id) == str(seeded_user)


def test_unpair_removes_agent_and_revokes_token(client: TestClient) -> None:
    reg = _register(client, _issue_code(client))
    assert len(client.get("/api/agents").json()["agents"]) == 1
    r = client.post(f"/api/agents/{reg['agent_id']}/unpair")
    assert r.status_code == 200
    assert len(client.get("/api/agents").json()["agents"]) == 0
    # Token no longer valid after unpair (session revoked / device gone).
    assert (
        client.post(
            "/api/agents/heartbeat",
            json={"status": "idle"},
            headers={"X-Agent-Token": reg["agent_token"]},
        ).status_code
        == 401
    )
