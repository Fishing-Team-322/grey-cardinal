"""Thin async HTTP client for the YouGile REST API v2.

Per-key, multi-tenant. Business logic lives in the board adapter / discovery
use-cases — this client only makes requests, enforces the rate limit, retries
transient failures, and maps responses to domain exceptions.

Verified API contract (see memory yougile-api-verified):
  - Auth endpoints (/auth/*) need no Bearer; resource endpoints need it.
  - List endpoints return {paging:{count,limit,offset,next}, content:[...]}.
  - /tasks supports columnId / assignedTo filters; NO projectId filter.
  - Webhooks are unsigned; unsubscribe = PUT /webhooks/{id} {disabled:true}.
The api_key is never logged.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from brain_api.integrations.yougile.exceptions import (
    YouGileAuthError,
    YouGileConfigError,
    YouGileHTTPError,
    YouGileNotFound,
    YouGilePermissionError,
    YouGileServerError,
)
from brain_api.integrations.yougile.ratelimit import TokenBucket, bucket_for

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://yougile.com/api-v2"
_PAGE_LIMIT = 50


class YouGileClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        rate_per_minute: int = 50,
        bucket: TokenBucket | None = None,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._bucket = bucket or bucket_for(api_key or "anon", rate_per_minute)
        self._transport = transport
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep_fn
        self._timeout = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=30.0)

    @property
    def rate_limit_remaining(self) -> int:
        return self._bucket.remaining()

    # ── core ──────────────────────────────────────────────────────────────────
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        auth: bool = True,
    ) -> Any:
        if auth and not self._api_key:
            raise YouGileConfigError("YouGile client used without an API key")
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._api_key}"
        url = self._base + path

        attempt = 0
        while True:
            await self._bucket.acquire()
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, transport=self._transport
                ) as client:
                    resp = await client.request(
                        method, url, json=json, params=params, headers=headers
                    )
            except httpx.HTTPError as exc:
                if attempt < self._max_retries:
                    await self._sleep(self._backoff_base * (2**attempt))
                    attempt += 1
                    continue
                logger.warning("YouGile %s %s network error: %s", method, path, type(exc).__name__)
                raise YouGileServerError(method, path, None, type(exc).__name__) from exc

            code = resp.status_code
            if code == 429:
                await self._sleep(_retry_after(resp))
                continue  # rate-limited by server: wait and retry, don't count as failure
            if 500 <= code < 600:
                if attempt < self._max_retries:
                    await self._sleep(self._backoff_base * (2**attempt))
                    attempt += 1
                    continue
                raise YouGileServerError(method, path, code, resp.text)
            if code >= 400:
                self._raise_for_4xx(method, path, code, resp.text)
            return resp.json() if resp.content else {}

    @staticmethod
    def _raise_for_4xx(method: str, path: str, code: int, body: str) -> None:
        logger.warning("YouGile %s %s failed: HTTP %s", method, path, code)
        if code == 401:
            raise YouGileAuthError(method, path, code, body)
        if code == 403:
            raise YouGilePermissionError(method, path, code, body)
        if code == 404:
            raise YouGileNotFound(method, path, code, body)
        raise YouGileHTTPError(method, path, code, body)

    async def _paginate(self, path: str, params: dict | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        params = dict(params or {})
        while True:
            params.update({"limit": _PAGE_LIMIT, "offset": offset})
            data = await self._request("GET", path, params=params)
            if not isinstance(data, dict):
                return data if isinstance(data, list) else items
            content = data.get("content", [])
            items.extend(content)
            paging = data.get("paging") or {}
            if not paging.get("next"):
                break
            offset += _PAGE_LIMIT
        return items

    # ── auth (no Bearer) ────────────────────────────────────────────────────────
    async def auth_companies(self, login: str, password: str) -> list[dict[str, Any]]:
        data = await self._request(
            "POST", "/auth/companies", json={"login": login, "password": password}, auth=False
        )
        return data.get("content", []) if isinstance(data, dict) else data

    async def auth_keys_get(self, login: str, password: str, company_id: str) -> list[dict[str, Any]]:
        return await self._request(
            "POST",
            "/auth/keys/get",
            json={"login": login, "password": password, "companyId": company_id},
            auth=False,
        )

    async def auth_keys_create(self, login: str, password: str, company_id: str) -> str:
        data = await self._request(
            "POST",
            "/auth/keys",
            json={"login": login, "password": password, "companyId": company_id},
            auth=False,
        )
        return data["key"]

    # ── projects / boards / columns ──────────────────────────────────────────────
    async def list_projects(self) -> list[dict[str, Any]]:
        return await self._paginate("/projects")

    async def get_project(self, project_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/projects/{project_id}")

    async def create_project(self, title: str, users: dict[str, str] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title}
        if users:
            body["users"] = users
        return await self._request("POST", "/projects", json=body)

    async def list_boards(self, project_id: str | None = None) -> list[dict[str, Any]]:
        params = {"projectId": project_id} if project_id else None
        return await self._paginate("/boards", params)

    async def create_board(self, title: str, project_id: str) -> dict[str, Any]:
        return await self._request("POST", "/boards", json={"title": title, "projectId": project_id})

    async def list_columns(self, board_id: str | None = None) -> list[dict[str, Any]]:
        params = {"boardId": board_id} if board_id else None
        return await self._paginate("/columns", params)

    async def create_column(self, title: str, board_id: str, color: int = 1) -> dict[str, Any]:
        return await self._request(
            "POST", "/columns", json={"title": title, "boardId": board_id, "color": color}
        )

    # ── tasks ────────────────────────────────────────────────────────────────────
    async def list_tasks(
        self, *, column_id: str | None = None, assigned_to: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if column_id:
            params["columnId"] = column_id
        if assigned_to:
            params["assignedTo"] = assigned_to
        return await self._paginate("/tasks", params or None)

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/tasks/{task_id}")

    async def create_task(
        self,
        title: str,
        column_id: str,
        *,
        description: str | None = None,
        assigned: list[str] | None = None,
        deadline: dict | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title, "columnId": column_id}
        if description:
            body["description"] = description
        if assigned:
            body["assigned"] = assigned
        if deadline:
            body["deadline"] = deadline
        return await self._request("POST", "/tasks", json=body)

    async def update_task(self, task_id: str, **fields: Any) -> dict[str, Any]:
        return await self._request("PUT", f"/tasks/{task_id}", json=fields)

    # ── users ────────────────────────────────────────────────────────────────────
    async def list_users(self) -> list[dict[str, Any]]:
        return await self._paginate("/users")

    # ── webhooks (unsigned; disable via PUT, no DELETE) ──────────────────────────
    async def list_webhooks(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/webhooks")
        return data if isinstance(data, list) else data.get("content", [])

    async def create_webhook(self, url: str, event: str) -> dict[str, Any]:
        return await self._request("POST", "/webhooks", json={"url": url, "event": event})

    async def disable_webhook(self, webhook_id: str) -> dict[str, Any]:
        return await self._request("PUT", f"/webhooks/{webhook_id}", json={"disabled": True})


def _retry_after(resp: httpx.Response) -> float:
    raw = resp.headers.get("Retry-After")
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return 5.0
