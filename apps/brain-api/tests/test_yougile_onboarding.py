"""YouGile onboarding endpoints: login -> connect -> status -> disconnect."""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.deps import get_container
from brain_api.api.routes import yougile as yg_routes
from brain_api.api.routes.accounts import get_current_user, get_db
from brain_api.infrastructure.db import models as m
from yougile_fakes import FakeYouGile


@pytest_asyncio.fixture
async def manager_and_team(session_factory):
    async with session_factory() as session:
        user = m.UserModel(id=uuid4(), display_name="Mgr", email="mgr@e.com", login="mgr")
        company = m.CompanyModel(id=uuid4(), name="C", timezone="Europe/Moscow", created_by=user.id)
        team = m.TeamModel(
            id=uuid4(), company_id=company.id, name="Team", timezone="Europe/Moscow",
            board_provider="yougile",
        )
        session.add_all([user, company, team])
        session.add(m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=user.id, role="manager"))
        await session.commit()
        return user.id, team.id


@pytest.fixture
def client(session_factory, manager_and_team, monkeypatch) -> TestClient:
    user_id, _ = manager_and_team
    fake = FakeYouGile(companies=[{"id": "co1", "name": "Acme"}], keys=[{"key": "k-existing"}])
    monkeypatch.setattr(yg_routes, "YouGileClient", lambda *a, **k: fake)

    async def _noop_discovery(*a, **k):
        return {"ok": True}

    monkeypatch.setattr(yg_routes, "discover_yougile_workspace", _noop_discovery)

    app = FastAPI()
    app.include_router(yg_routes.router)

    async def _db():
        async with session_factory() as session:
            yield session

    async def _user():
        async with session_factory() as session:
            return await session.get(m.UserModel, user_id)

    from types import SimpleNamespace

    fake_container = SimpleNamespace(session_factory=session_factory)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_container] = lambda: fake_container
    return TestClient(app)


def test_full_onboarding_flow(client: TestClient, manager_and_team):
    _, team_id = manager_and_team
    base = f"/api/teams/{team_id}/integrations/yougile"

    r = client.post(f"{base}/login", json={"login": "a@b.com", "password": "pw"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["companies"] == [{"id": "co1", "name": "Acme"}]
    token = body["onboarding_token"]

    r = client.post(f"{base}/connect", json={"onboarding_token": token, "company_id": "co1"})
    assert r.status_code == 200, r.text
    assert r.json()["connected"] is True
    assert r.json()["sync_status"] == "in_progress"

    r = client.get(f"{base}/status")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["connected"] is True
    assert s["company"]["name"] == "Acme"
    assert s["stats"] == {"projects": 0, "boards": 0, "columns": 0, "tasks": 0}

    r = client.request("DELETE", base)
    assert r.status_code == 200
    assert r.json()["connected"] is False
    r = client.get(f"{base}/status")
    assert r.json()["connected"] is False


def test_connect_with_expired_token_rejected(client: TestClient, manager_and_team):
    _, team_id = manager_and_team
    base = f"/api/teams/{team_id}/integrations/yougile"
    r = client.post(f"{base}/connect", json={"onboarding_token": "nope", "company_id": "co1"})
    assert r.status_code == 422
