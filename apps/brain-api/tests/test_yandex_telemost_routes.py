"""Yandex Telemost OAuth + room endpoints: status, connect, callback, create room.

Covers: not-connected status, connect/start returns a Yandex OAuth URL, callback
validates CSRF state and stores tokens encrypted, no token leakage in JSON, and
create-room error mapping (401→409, 5xx→502).
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.routes.accounts import get_current_user, get_db
from brain_api.api.routes.yandex_telemost import router as telemost_router
from brain_api.application.use_cases import yandex_telemost as svc
from brain_api.config import Settings
from brain_api.infrastructure.db import models as m
from brain_api.integrations.yandex_telemost import (
    TokenResponse,
    YandexTelemostAuthError,
    YandexTelemostTransientError,
)

CONFIGURED = Settings(
    yandex_telemost_client_id="cid",
    yandex_telemost_client_secret="sec",
    board_creds_encryption_key="unit-test-key-please-ignore",
    public_base_url="https://fishingteam.su",
)


class FakeClient:
    """Stand-in for YandexTelemostClient (no real HTTP)."""

    def __init__(self, *, create_exc: Exception | None = None) -> None:
        self._create_exc = create_exc

    def build_authorization_url(self, state: str) -> str:
        return f"https://oauth.yandex.ru/authorize?response_type=code&client_id=cid&state={state}"

    async def exchange_code_for_token(self, code: str) -> TokenResponse:
        return TokenResponse(
            access_token="ACCESS-XYZ",
            refresh_token="REFRESH-XYZ",
            expires_in=3600,
            scope="telemost-api:conferences.create",
            token_type="bearer",
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        return await self.exchange_code_for_token("x")

    async def create_conference(self, access_token: str, **kw):
        if self._create_exc is not None:
            raise self._create_exc
        return {"id": "conf-1", "join_url": "https://telemost.yandex.ru/j/abc"}


@pytest_asyncio.fixture
async def seeded(session_factory):
    """User who is a manager of a team."""
    async with session_factory() as session:
        user = m.UserModel(id=uuid4(), display_name="Boss", email="b@e.com", login="boss")
        session.add(user)
        await session.flush()
        company = m.CompanyModel(name="Co", timezone="Europe/Moscow", created_by=user.id)
        session.add(company)
        await session.flush()
        team = m.TeamModel(company_id=company.id, name="Team", timezone="Europe/Moscow")
        session.add(team)
        await session.flush()
        session.add(m.TeamMemberModel(team_id=team.id, user_id=user.id, role="manager"))
        await session.commit()
        return {"user_id": user.id, "team_id": team.id}


@pytest.fixture
def client(session_factory, seeded, monkeypatch) -> TestClient:
    monkeypatch.setattr("brain_api.api.routes.yandex_telemost.get_settings", lambda: CONFIGURED)

    app = FastAPI()
    app.include_router(telemost_router)

    async def _override_db():
        async with session_factory() as session:
            yield session

    async def _override_user():
        async with session_factory() as session:
            return await session.get(m.UserModel, seeded["user_id"])

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return TestClient(app)


def _no_token_anywhere(payload: dict) -> None:
    blob = json.dumps(payload)
    assert "ACCESS-XYZ" not in blob
    assert "REFRESH-XYZ" not in blob
    assert "access_token" not in payload
    assert "refresh_token" not in payload


def test_status_not_connected(client: TestClient, seeded) -> None:
    r = client.get("/api/integrations/yandex-telemost/status", params={"team_id": str(seeded["team_id"])})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is False
    assert body["status"] == "disconnected"
    _no_token_anywhere(body)


def test_connect_start_returns_oauth_url(client: TestClient, seeded, monkeypatch) -> None:
    monkeypatch.setattr(svc, "build_client", lambda settings: FakeClient())
    r = client.post(
        "/api/integrations/yandex-telemost/connect/start",
        json={"team_id": str(seeded["team_id"])},
    )
    assert r.status_code == 200, r.text
    assert r.json()["authorization_url"].startswith("https://oauth.yandex.ru/authorize")


def test_connect_start_400_when_not_configured(session_factory, seeded, monkeypatch) -> None:
    # Unconfigured settings (no client id/secret) => 400, no OAuth url.
    monkeypatch.setattr(
        "brain_api.api.routes.yandex_telemost.get_settings", lambda: Settings()
    )
    app = FastAPI()
    app.include_router(telemost_router)

    async def _db():
        async with session_factory() as s:
            yield s

    async def _user():
        async with session_factory() as s:
            return await s.get(m.UserModel, seeded["user_id"])

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    c = TestClient(app)
    r = c.post("/api/integrations/yandex-telemost/connect/start", json={"team_id": str(seeded["team_id"])})
    assert r.status_code == 400


def test_callback_rejects_bad_state(client: TestClient) -> None:
    r = client.get(
        "/api/integrations/yandex-telemost/oauth/callback",
        params={"code": "c", "state": "does-not-exist"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "error=state" in r.headers["location"]


@pytest.mark.asyncio
async def test_callback_exchanges_and_stores_encrypted_token(
    client: TestClient, seeded, session_factory, monkeypatch
) -> None:
    monkeypatch.setattr(svc, "build_client", lambda settings: FakeClient())
    # 1) start to mint a valid state
    start = client.post(
        "/api/integrations/yandex-telemost/connect/start",
        json={"team_id": str(seeded["team_id"])},
    )
    state = start.json()["authorization_url"].split("state=")[1]

    # 2) callback with the real state
    cb = client.get(
        "/api/integrations/yandex-telemost/oauth/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert cb.status_code == 302
    assert "connected=1" in cb.headers["location"]

    # tokens stored, encrypted (not plaintext), decryptable
    async with session_factory() as session:
        integ = await svc.get_integration(session, seeded["team_id"])
        assert integ is not None and integ.status == "connected"
        assert integ.access_token_encrypted is not None
        assert b"ACCESS-XYZ" not in integ.access_token_encrypted  # encrypted at rest
        from brain_api.infrastructure.security.encryption import SecretCipher

        cipher = SecretCipher(CONFIGURED.board_creds_encryption_key)
        assert cipher.decrypt_text(integ.access_token_encrypted) == "ACCESS-XYZ"

    # status now connected, still no token leakage
    st = client.get(
        "/api/integrations/yandex-telemost/status", params={"team_id": str(seeded["team_id"])}
    ).json()
    assert st["connected"] is True
    _no_token_anywhere(st)


def test_state_is_one_time(client: TestClient, seeded, monkeypatch) -> None:
    monkeypatch.setattr(svc, "build_client", lambda settings: FakeClient())
    start = client.post(
        "/api/integrations/yandex-telemost/connect/start",
        json={"team_id": str(seeded["team_id"])},
    )
    state = start.json()["authorization_url"].split("state=")[1]
    first = client.get(
        "/api/integrations/yandex-telemost/oauth/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    assert "connected=1" in first.headers["location"]
    second = client.get(
        "/api/integrations/yandex-telemost/oauth/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    assert "error=state" in second.headers["location"]


def _connect(client: TestClient, seeded, monkeypatch) -> None:
    monkeypatch.setattr(svc, "build_client", lambda settings: FakeClient())
    start = client.post(
        "/api/integrations/yandex-telemost/connect/start",
        json={"team_id": str(seeded["team_id"])},
    )
    state = start.json()["authorization_url"].split("state=")[1]
    client.get(
        "/api/integrations/yandex-telemost/oauth/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )


def test_create_room_calls_client(client: TestClient, seeded, monkeypatch) -> None:
    _connect(client, seeded, monkeypatch)
    r = client.post(
        "/api/integrations/yandex-telemost/test-create-room",
        json={"team_id": str(seeded["team_id"])},
    )
    assert r.status_code == 200, r.text
    assert r.json()["join_url"] == "https://telemost.yandex.ru/j/abc"


def test_create_room_401_maps_to_409(client: TestClient, seeded, monkeypatch) -> None:
    _connect(client, seeded, monkeypatch)
    monkeypatch.setattr(
        svc,
        "build_client",
        lambda settings: FakeClient(create_exc=YandexTelemostAuthError("POST", "u", 401, "no")),
    )
    r = client.post(
        "/api/integrations/yandex-telemost/test-create-room",
        json={"team_id": str(seeded["team_id"])},
    )
    assert r.status_code == 409


def test_create_room_5xx_maps_to_502(client: TestClient, seeded, monkeypatch) -> None:
    _connect(client, seeded, monkeypatch)
    monkeypatch.setattr(
        svc,
        "build_client",
        lambda settings: FakeClient(create_exc=YandexTelemostTransientError("POST", "u", 503, "x")),
    )
    r = client.post(
        "/api/integrations/yandex-telemost/test-create-room",
        json={"team_id": str(seeded["team_id"])},
    )
    assert r.status_code == 502


def test_disconnect(client: TestClient, seeded, monkeypatch) -> None:
    _connect(client, seeded, monkeypatch)
    r = client.post(
        "/api/integrations/yandex-telemost/disconnect", json={"team_id": str(seeded["team_id"])}
    )
    assert r.status_code == 200
    st = client.get(
        "/api/integrations/yandex-telemost/status", params={"team_id": str(seeded["team_id"])}
    ).json()
    assert st["connected"] is False
