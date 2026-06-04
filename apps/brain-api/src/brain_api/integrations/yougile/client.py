"""Async YouGile REST API v2 client.

Docs: https://ru.yougile.com/api-v2

- Auth: Authorization: Bearer <api_key>
- Timeouts on every request.
- All HTTP/network errors are wrapped in YouGileHTTPError and logged
  WITHOUT secrets (the api_key is never logged).
- The client never calls out when YouGile is not effective_enabled — callers
  (YouGileBoardService) guard that, but health_check double-checks.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from brain_api.integrations.yougile.exceptions import YouGileConfigError, YouGileHTTPError
from brain_api.integrations.yougile.models import YouGileConfig, YouGileHealth

logger = logging.getLogger(__name__)


class YouGileClient:
    def __init__(self, config: YouGileConfig) -> None:
        self._config = config
        self._base = config.api_base_v2

    # ------------------------------------------------------------------ #
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, json: dict | None = None) -> Any:
        if not self._config.configured:
            raise YouGileConfigError("YouGile client used while not configured")
        url = self._base + path
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout) as client:
                response = await client.request(method, url, json=json, headers=self._headers())
                response.raise_for_status()
                return response.json() if response.content else {}
        except httpx.HTTPStatusError as exc:
            logger.warning("YouGile %s %s failed: HTTP %s", method, path, exc.response.status_code)
            raise YouGileHTTPError(
                method, path, exc.response.status_code, exc.response.text
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("YouGile %s %s network error: %s", method, path, type(exc).__name__)
            raise YouGileHTTPError(method, path, None, str(exc)) from exc

    # ------------------------------------------------------------------ #
    # Health / discovery
    # ------------------------------------------------------------------ #

    async def health_check(self) -> YouGileHealth:
        """Lightweight connectivity probe via GET /projects."""
        if not self._config.effective_enabled:
            return YouGileHealth(
                ok=False, status="disabled", reason="YouGile is not enabled/configured"
            )
        try:
            await self._request("GET", "/projects")
            return YouGileHealth(
                ok=True,
                status="connected",
                detail={
                    "company_id": self._config.company_id,
                    "project_id": self._config.project_id,
                    "board_id": self._config.board_id,
                },
            )
        except YouGileHTTPError as exc:
            return YouGileHealth(ok=False, status="error", reason=str(exc))

    async def get_projects(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/projects")
        return data.get("content", data) if isinstance(data, dict) else data

    async def get_boards(self, project_id: str | None = None) -> list[dict[str, Any]]:
        path = "/boards"
        if project_id:
            path += f"?projectId={project_id}"
        data = await self._request("GET", path)
        return data.get("content", data) if isinstance(data, dict) else data

    async def get_columns(self, board_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/columns?boardId={board_id}")
        return data.get("content", data) if isinstance(data, dict) else data

    # ------------------------------------------------------------------ #
    # Tasks
    # ------------------------------------------------------------------ #

    async def create_task(
        self,
        column_id: str,
        title: str,
        description: str = "",
        assigned: list[str] | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title, "columnId": column_id, "description": description}
        if assigned:
            body["assigned"] = assigned
        data = await self._request("POST", "/tasks", json=body)
        if not isinstance(data, dict) or not data.get("id"):
            raise YouGileHTTPError("POST", "/tasks", 200, f"unexpected create response: {data}")
        return data

    async def move_task(self, task_id: str, column_id: str) -> dict[str, Any]:
        return await self._request("PUT", f"/tasks/{task_id}", json={"columnId": column_id})

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/tasks/{task_id}")
