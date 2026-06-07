"""Agent pairing lifecycle — DB-backed, tenant-scoped (replaces the demo store).

Covers: pairing-code issuance (JWT), register (one-time/expiry), heartbeat auth +
last_seen update, listing, unpair + token revocation, and that the token issued by
/register is a real ClientSession bound to the pairing user — the same token the
daemon endpoints consume (correct, non-global binding).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.routes.accounts import get_current_user, get_db
from brain_api.api.routes.agents import router as agents_router
from brain_api.api.routes.daemon import _agent_team, _resolve_session
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


@pytest.fixture
def unauth_client(session_factory) -> TestClient:
    """Same router but WITHOUT the auth override — exercises the real
    get_current_user dependency (no session cookie => 401)."""
    app = FastAPI()
    app.include_router(agents_router)

    async def _override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


async def _seed_team(session, *, owner_id, name: str, tg_chat_id: int):
    """A self-contained tenant: company + team (with Telegram chat) + one member."""
    company = m.CompanyModel(name=f"{name} Co", timezone="Europe/Moscow", created_by=owner_id)
    session.add(company)
    await session.flush()
    team = m.TeamModel(
        company_id=company.id, name=name, timezone="Europe/Moscow", tg_chat_id=tg_chat_id
    )
    session.add(team)
    await session.flush()
    session.add(m.TeamMemberModel(team_id=team.id, user_id=owner_id, role="manager"))
    return team.id


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


def test_pairing_code_requires_auth(unauth_client: TestClient) -> None:
    """No session cookie => no pairing code. Codes are minted only for the
    authenticated user who will own (and be billed/attributed for) the agent."""
    r = unauth_client.post("/api/agents/pairing-code")
    assert r.status_code == 401


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


def test_unpair_removes_agent_and_revokes_token(
    client: TestClient, session_factory
) -> None:
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

    async def assert_session_revoked() -> None:
        async with session_factory() as session:
            client_session = await session.get(m.ClientSessionModel, UUID(reg["agent_token"]))
            assert client_session is not None
            assert client_session.status == "revoked"
            assert client_session.device_id is None

    asyncio.run(assert_session_revoked())


@pytest.mark.asyncio
async def test_agent_upload_routes_to_bound_users_team_only(
    client: TestClient, session_factory, seeded_user
):
    """An agent paired by user A must route daemon uploads to A's team — and the
    routing helper must resolve a *different* user to their *own* team. This proves
    upload destination follows the per-agent token binding, with no global/
    single-tenant fallback that could leak one tenant's audio into another's board.
    """
    # Two independent tenants, each with its own Telegram-bound team.
    async with session_factory() as session:
        other_user = m.UserModel(
            id=uuid4(), display_name="Bob", email="bob@example.com", login="bob"
        )
        session.add(other_user)
        await session.flush()
        other_user_id = other_user.id
        team_a = await _seed_team(session, owner_id=seeded_user, name="Team A", tg_chat_id=-1001)
        team_b = await _seed_team(session, owner_id=other_user_id, name="Team B", tg_chat_id=-1002)
        await session.commit()

    # Agent is paired by user A (seeded_user).
    reg = _register(client, _issue_code(client))

    async with session_factory() as session:
        cs = await _resolve_session(session, reg["agent_token"])
        assert cs is not None
        assert cs.user_id == seeded_user  # token bound to A, not a global session

        # daemon_v2_upload picks the destination team via _agent_team(cs.user_id):
        bound_team = await _agent_team(session, cs.user_id)
        assert bound_team is not None and bound_team.id == team_a

        # The other tenant resolves strictly to its own team — no cross-tenant bleed.
        other_team = await _agent_team(session, other_user_id)
        assert other_team is not None and other_team.id == team_b
        assert other_team.id != bound_team.id
