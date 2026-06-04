"""YouGile board service — business logic over the YouGile client.

Bridges the demo brain pipeline (local tasks) with YouGile:
  - confirm proposal  → create_task in the TODO column
  - move task         → move_task to the matching column
  - manual re-sync    → retry a failed/disabled task

When YouGile is not enabled/configured, every method returns a SyncResult with
status "disabled" and the local board keeps working unchanged.

Move policy: local board is the source of truth. A failed YouGile move does NOT
roll back the local move — it records yougile_status="error" so it stays visible
and can be retried via POST /api/tasks/{id}/sync-yougile.
"""

from __future__ import annotations

import logging
from typing import Any

from brain_api.integrations.yougile.client import YouGileClient
from brain_api.integrations.yougile.exceptions import YouGileError
from brain_api.integrations.yougile.models import SyncResult, YouGileConfig, YouGileHealth

logger = logging.getLogger(__name__)


class YouGileBoardService:
    def __init__(self, config: YouGileConfig, client: Any | None = None) -> None:
        self._config = config
        if client is not None:
            self._client = client
        elif config.configured:
            self._client = YouGileClient(config)
        else:
            self._client = None

    # ------------------------------------------------------------------ #
    @property
    def config(self) -> YouGileConfig:
        return self._config

    def is_enabled(self) -> bool:
        return self._config.effective_enabled

    # ------------------------------------------------------------------ #
    # Health / discovery
    # ------------------------------------------------------------------ #

    async def health(self) -> YouGileHealth:
        if not self._config.effective_enabled or self._client is None:
            reason = (
                "YOUGILE_ENABLED is false"
                if not self._config.enabled
                else "YouGile env vars are not configured"
            )
            return YouGileHealth(ok=False, status="disabled", reason=reason)
        return await self._client.health_check()

    async def columns_status(self) -> dict[str, Any]:
        """Return configured column IDs and, if enabled, verify them via the API."""
        configured = {
            "todo": self._config.column_todo_id,
            "in_progress": self._config.column_in_progress_id,
            "done": self._config.column_done_id,
        }
        result: dict[str, Any] = {
            "configured_columns": configured,
            "board_id": self._config.board_id,
            "verified": False,
        }
        if not self._config.effective_enabled or self._client is None or not self._config.board_id:
            return result
        try:
            remote = await self._client.get_columns(self._config.board_id)
            remote_ids = {str(c.get("id")) for c in remote if isinstance(c, dict)}
            result["verified"] = True
            result["columns_found"] = {
                name: (cid in remote_ids) for name, cid in configured.items() if cid
            }
        except YouGileError as exc:
            result["error"] = str(exc)
        return result

    # ------------------------------------------------------------------ #
    # Sync on confirm / move
    # ------------------------------------------------------------------ #

    async def sync_task_on_confirm(self, task: dict[str, Any]) -> SyncResult:
        if not self._config.effective_enabled or self._client is None:
            return SyncResult(yougile_status="disabled")
        title = task.get("title", "").strip() or "(no title)"
        description = self.build_description(task)
        assigned = self.resolve_assigned(task.get("assignee", ""))
        try:
            data = await self._client.create_task(
                self._config.column_todo_id, title, description, assigned
            )
            return SyncResult(yougile_status="synced", yougile_task_id=str(data["id"]))
        except YouGileError as exc:
            logger.warning("YouGile create_task failed for task %s", task.get("task_id"))
            return SyncResult(yougile_status="error", yougile_error=str(exc))

    async def sync_task_move(self, task: dict[str, Any], new_status: str) -> SyncResult:
        if not self._config.effective_enabled or self._client is None:
            return SyncResult(yougile_status="disabled")
        yt_id = task.get("yougile_task_id", "")
        if not yt_id:
            return SyncResult(
                yougile_status="error",
                yougile_error="task is not synced to YouGile (no yougile_task_id)",
            )
        column_id = self._config.column_for(new_status)
        if not column_id:
            return SyncResult(
                yougile_status="error",
                yougile_task_id=yt_id,
                yougile_error=f"no YouGile column configured for status '{new_status}'",
            )
        try:
            await self._client.move_task(yt_id, column_id)
            return SyncResult(yougile_status="synced", yougile_task_id=yt_id)
        except YouGileError as exc:
            logger.warning("YouGile move_task failed for task %s", task.get("task_id"))
            return SyncResult(yougile_status="error", yougile_task_id=yt_id, yougile_error=str(exc))

    def get_sync_status(self, task: dict[str, Any]) -> dict[str, str]:
        return {
            "yougile_status": task.get("yougile_status", "disabled"),
            "yougile_task_id": task.get("yougile_task_id", ""),
            "yougile_error": task.get("yougile_error", ""),
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def build_description(self, task: dict[str, Any]) -> str:
        lines = ["Created by Grey Cardinal"]
        if task.get("source"):
            lines.append(f"Source: {task['source']}")
        if task.get("proposal_id"):
            lines.append(f"Proposal: {task['proposal_id']}")
        if task.get("meeting_id"):
            lines.append(f"Meeting: {task['meeting_id']}")
        if task.get("chat_id"):
            lines.append(f"Chat: {task['chat_id']}")
        if task.get("assignee"):
            lines.append(f"Assignee: {task['assignee']}")
        if task.get("deadline"):
            lines.append(f"Deadline: {task['deadline']}")
        if task.get("confidence") is not None:
            lines.append(f"Confidence: {task['confidence']}")
        return "\n".join(lines)

    def resolve_assigned(self, assignee: str) -> list[str]:
        uid = self._config.user_map.get(assignee)
        return [uid] if uid else []


# --------------------------------------------------------------------------- #
# Singleton (overridable in tests)
# --------------------------------------------------------------------------- #

_service: YouGileBoardService | None = None


def get_yougile_service() -> YouGileBoardService:
    global _service
    if _service is None:
        from brain_api.config import get_settings

        _service = YouGileBoardService(YouGileConfig.from_settings(get_settings()))
    return _service


def set_yougile_service(service: YouGileBoardService) -> None:
    global _service
    _service = service


def reset_yougile_service() -> None:
    global _service
    _service = None
