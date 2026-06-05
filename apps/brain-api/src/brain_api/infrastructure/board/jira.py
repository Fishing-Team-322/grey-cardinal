"""Jira Cloud board gateway.

Implements BoardGateway protocol for Atlassian Jira Cloud (REST API v3).
Auth: Basic Auth with email + API token.

Required env vars:
  JIRA_URL          — https://myteam.atlassian.net
  JIRA_EMAIL        — Atlassian account email
  JIRA_API_TOKEN    — from id.atlassian.com/manage-profile/security/api-tokens
  JIRA_PROJECT_KEY  — project key, e.g. PROJ
  JIRA_DONE_TRANSITION_ID        — transition ID for Done (default 31)
  JIRA_IN_PROGRESS_TRANSITION_ID — transition ID for In Progress (default 21)
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskPriority, TaskStatus
from grey_cardinal_contracts import BoardCardResult
from grey_cardinal_contracts.board import BoardProvider

logger = logging.getLogger(__name__)

_PRIORITY_MAP: dict[TaskPriority, str] = {
    TaskPriority.critical: "Highest",
    TaskPriority.high: "High",
    TaskPriority.medium: "Medium",
    TaskPriority.low: "Low",
}


@dataclass(frozen=True, slots=True)
class JiraConfig:
    url: str
    email: str
    api_token: str
    project_key: str
    done_transition_id: str = "31"
    in_progress_transition_id: str = "21"

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.email and self.api_token and self.project_key)

    @property
    def auth_header(self) -> str:
        creds = f"{self.email}:{self.api_token}"
        return "Basic " + base64.b64encode(creds.encode()).decode()


class JiraBoardGateway:
    """BoardGateway implementation for Jira Cloud."""

    def __init__(self, config: JiraConfig) -> None:
        self._cfg = config

    async def create_card(self, task: Task) -> BoardCardResult:
        if not self._cfg.is_configured:
            logger.warning("Jira not configured — returning mock result")
            return BoardCardResult(
                provider=BoardProvider.jira,
                external_card_id="UNCONFIGURED",
                external_url=None,
            )

        priority = _PRIORITY_MAP.get(task.priority, "Medium")
        desc_text = "Создано автоматически Grey Cardinal PM-агентом."
        if task.assignee_text:
            desc_text += f"\nИсполнитель: {task.assignee_text}"

        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": self._cfg.project_key},
                "summary": task.title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": desc_text}]}
                    ],
                },
                "issuetype": {"name": "Task"},
                "priority": {"name": priority},
            }
        }

        data = await self._post("/rest/api/3/issue", payload)
        if not data:
            return BoardCardResult(
                provider=BoardProvider.jira,
                external_card_id="ERROR",
                external_url=None,
            )

        key = data.get("key", "UNKNOWN")
        url = f"{self._cfg.url.rstrip('/')}/browse/{key}"
        logger.info("Jira issue created: %s", key)
        return BoardCardResult(
            provider=BoardProvider.jira,
            external_card_id=key,
            external_url=url,
        )

    async def move_card(self, external_card_id: str, status: TaskStatus) -> None:
        if not self._cfg.is_configured or not external_card_id:
            return
        tid = {
            TaskStatus.done: self._cfg.done_transition_id,
            TaskStatus.in_progress: self._cfg.in_progress_transition_id,
        }.get(status)
        if not tid:
            return
        await self._post(
            f"/rest/api/3/issue/{external_card_id}/transitions",
            {"transition": {"id": tid}},
        )
        logger.info("Jira %s → %s", external_card_id, status)

    async def _post(self, path: str, payload: dict) -> dict | None:
        url = self._cfg.url.rstrip("/") + path
        headers = {
            "Authorization": self._cfg.auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code in (200, 201, 204):
                    return r.json() if r.content else {}
                logger.warning("Jira %s → %s: %s", path, r.status_code, r.text[:200])
        except httpx.HTTPError as exc:
            logger.error("Jira request failed: %s", exc)
        return None
