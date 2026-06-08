"""Async client for Yandex OAuth + Telemost conferences API.

Two upstreams:
  - OAuth: https://oauth.yandex.ru/{authorize,token}
  - Telemost: https://cloud-api.yandex.net/v1/telemost-api/conferences
    auth header is `Authorization: OAuth <access_token>` (NOT Bearer).

Secrets discipline: client_secret and tokens are NEVER logged and never put into
exception messages (only method/url/status/truncated body). The client makes
requests and maps responses to domain exceptions; storage/refresh orchestration
lives in the use-case layer.

Docs spike on the "Конспект встреч в Телемосте с Алисой Про" summary feature:
see docs/yandex-telemost-alice-summary-spike.md (out of scope for MVP).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

OAUTH_AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
OAUTH_TOKEN_URL = "https://oauth.yandex.ru/token"
TELEMOST_CONFERENCES_URL = "https://cloud-api.yandex.net/v1/telemost-api/conferences"


# ── Exceptions ────────────────────────────────────────────────────────────────


class YandexTelemostError(Exception):
    """Base class. Carries no secrets."""


class YandexTelemostConfigError(YandexTelemostError):
    """Client used without client_id / client_secret."""


class YandexTelemostHTTPError(YandexTelemostError):
    def __init__(self, method: str, url: str, status: int | None, body: str) -> None:
        self.method = method
        self.url = url
        self.status = status
        self.body = (body or "")[:500]
        code = status if status is not None else "network-error"
        super().__init__(f"Yandex {method} {url} -> {code}: {self.body}")


class YandexTelemostAuthError(YandexTelemostHTTPError):
    """401 — access token invalid/expired; integration must reconnect."""


class YandexTelemostForbiddenError(YandexTelemostHTTPError):
    """403 — token valid but missing scope / no access."""


class YandexTelemostRateLimited(YandexTelemostHTTPError):
    """429 — caller should back off and retry later."""


class YandexTelemostTransientError(YandexTelemostHTTPError):
    """5xx or network/timeout — transient, retry later."""


# ── Token DTO ─────────────────────────────────────────────────────────────────


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    scope: str | None
    token_type: str | None

    @property
    def expires_at(self) -> datetime | None:
        if not self.expires_in:
            return None
        return datetime.now(UTC) + timedelta(seconds=int(self.expires_in))

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TokenResponse:
        return cls(
            access_token=str(data.get("access_token") or ""),
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope"),
            token_type=data.get("token_type"),
        )


# ── Client ────────────────────────────────────────────────────────────────────


class YandexTelemostClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not client_id or not client_secret:
            raise YandexTelemostConfigError("client_id and client_secret are required")
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._scopes = scopes
        self._transport = transport
        self._timeout = timeout

    # ── OAuth ──

    def build_authorization_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "scope": self._scopes,
            "state": state,
            "force_confirm": "yes",
        }
        return f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> TokenResponse:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
            }
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        return await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        )

    async def _token_request(self, form: dict[str, str]) -> TokenResponse:
        async with self._http() as client:
            try:
                resp = await client.post(
                    OAUTH_TOKEN_URL,
                    data=form,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            except httpx.HTTPError as exc:
                raise YandexTelemostTransientError("POST", OAUTH_TOKEN_URL, None, str(exc)) from exc
        self._raise_for_status("POST", OAUTH_TOKEN_URL, resp)
        return TokenResponse.from_json(resp.json())

    # ── Telemost conferences ──

    async def create_conference(
        self,
        access_token: str,
        *,
        title: str | None = None,
        description: str | None = None,
        starts_at: datetime | None = None,
        duration: int | None = None,
        access_level: str = "PUBLIC",
    ) -> dict[str, Any]:
        # The create-conference endpoint does not accept meeting title, description,
        # start time, or duration. Those belong to Calendar/live-stream flows.
        # Keep the compatibility arguments for callers, but never send unsupported
        # fields: Yandex rejects the whole request with 4xx when they are present.
        del title, description, starts_at, duration
        payload: dict[str, Any] = {"waiting_room_level": access_level}
        return await self._authed("POST", TELEMOST_CONFERENCES_URL, access_token, json=payload)

    async def read_conference(self, access_token: str, conference_id: str) -> dict[str, Any]:
        url = f"{TELEMOST_CONFERENCES_URL}/{conference_id}"
        return await self._authed("GET", url, access_token)

    async def _authed(
        self, method: str, url: str, access_token: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"OAuth {access_token}",
            "Content-Type": "application/json",
        }
        async with self._http() as client:
            try:
                resp = await client.request(method, url, headers=headers, json=json)
            except httpx.HTTPError as exc:
                raise YandexTelemostTransientError(method, url, None, str(exc)) from exc
        self._raise_for_status(method, url, resp)
        if not resp.content:
            return {}
        return resp.json()

    # ── Internals ──

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=self._timeout)

    @staticmethod
    def _raise_for_status(method: str, url: str, resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        body = resp.text
        status = resp.status_code
        if status == 401:
            raise YandexTelemostAuthError(method, url, status, body)
        if status == 403:
            raise YandexTelemostForbiddenError(method, url, status, body)
        if status == 429:
            raise YandexTelemostRateLimited(method, url, status, body)
        if status >= 500:
            raise YandexTelemostTransientError(method, url, status, body)
        raise YandexTelemostHTTPError(method, url, status, body)
