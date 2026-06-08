"""YandexTelemostClient: URL building, token parsing, and HTTP error mapping."""

from __future__ import annotations

import httpx
import pytest

from brain_api.integrations.yandex_telemost import (
    OAUTH_TOKEN_URL,
    TELEMOST_CONFERENCES_URL,
    YandexTelemostAuthError,
    YandexTelemostClient,
    YandexTelemostConfigError,
    YandexTelemostForbiddenError,
    YandexTelemostHTTPError,
    YandexTelemostRateLimited,
    YandexTelemostTransientError,
)


def _client(handler) -> YandexTelemostClient:
    return YandexTelemostClient(
        client_id="cid",
        client_secret="secret",
        redirect_uri="https://fishingteam.su/api/integrations/yandex-telemost/oauth/callback",
        scopes="telemost-api:conferences.create telemost-api:conferences.read",
        transport=httpx.MockTransport(handler),
    )


def test_requires_credentials() -> None:
    with pytest.raises(YandexTelemostConfigError):
        YandexTelemostClient(client_id="", client_secret="", redirect_uri="x", scopes="y")


def test_build_authorization_url_has_required_params() -> None:
    client = _client(lambda req: httpx.Response(200, json={}))
    url = client.build_authorization_url("st-123")
    assert url.startswith("https://oauth.yandex.ru/authorize?")
    assert "response_type=code" in url
    assert "client_id=cid" in url
    assert "state=st-123" in url
    assert "redirect_uri=https%3A%2F%2Ffishingteam.su" in url
    assert "telemost-api" in url


@pytest.mark.asyncio
async def test_exchange_code_for_token_parses_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == OAUTH_TOKEN_URL
        assert b"grant_type=authorization_code" in request.content
        assert b"client_secret=secret" in request.content
        return httpx.Response(
            200,
            json={
                "access_token": "AT",
                "refresh_token": "RT",
                "expires_in": 3600,
                "scope": "telemost-api:conferences.create",
                "token_type": "bearer",
            },
        )

    token = await _client(handler).exchange_code_for_token("code-1")
    assert token.access_token == "AT"
    assert token.refresh_token == "RT"
    assert token.expires_at is not None


@pytest.mark.asyncio
async def test_create_conference_sends_oauth_header_and_returns_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == TELEMOST_CONFERENCES_URL
        assert request.headers["Authorization"] == "OAuth AT"
        assert request.read() == b'{"waiting_room_level":"PUBLIC"}'
        return httpx.Response(201, json={"id": "conf-1", "join_url": "https://telemost.yandex.ru/j/x"})

    data = await _client(handler).create_conference(
        "AT",
        title="Sync",
        description="Unsupported for a conference",
        duration=60,
    )
    assert data["id"] == "conf-1"
    assert data["join_url"].startswith("https://telemost.yandex.ru/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,exc",
    [
        (401, YandexTelemostAuthError),
        (403, YandexTelemostForbiddenError),
        (429, YandexTelemostRateLimited),
        (500, YandexTelemostTransientError),
        (503, YandexTelemostTransientError),
        (400, YandexTelemostHTTPError),
    ],
)
async def test_create_conference_maps_http_errors(status: int, exc: type[Exception]) -> None:
    client = _client(lambda req: httpx.Response(status, json={"message": "err"}))
    with pytest.raises(exc):
        await client.create_conference("AT")


@pytest.mark.asyncio
async def test_network_error_is_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(YandexTelemostTransientError):
        await _client(handler).create_conference("AT")


@pytest.mark.asyncio
async def test_error_messages_do_not_leak_token() -> None:
    client = _client(lambda req: httpx.Response(401, text="nope"))
    try:
        await client.create_conference("SUPER-SECRET-TOKEN")
    except YandexTelemostAuthError as exc:
        assert "SUPER-SECRET-TOKEN" not in str(exc)
