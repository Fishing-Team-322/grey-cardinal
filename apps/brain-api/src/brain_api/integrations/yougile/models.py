"""YouGile integration data models."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Local task status → which YouGile column env-id to use.
STATUS_TO_COLUMN_ATTR = {
    "todo": "column_todo_id",
    "in_progress": "column_in_progress_id",
    "done": "column_done_id",
}


@dataclass(frozen=True)
class YouGileConfig:
    """Resolved YouGile configuration.

    `enabled` is the explicit YOUGILE_ENABLED flag; `configured` means the
    required credentials are present. The client only calls out when both hold
    (`effective_enabled`).
    """

    enabled: bool
    api_base: str
    api_key: str
    company_id: str = ""
    project_id: str = ""
    board_id: str = ""
    column_todo_id: str = ""
    column_in_progress_id: str = ""
    column_done_id: str = ""
    user_map: dict[str, str] = field(default_factory=dict)
    timeout: float = 15.0

    @property
    def configured(self) -> bool:
        # Minimum needed to actually create a task in YouGile.
        return bool(self.api_key and self.column_todo_id)

    @property
    def effective_enabled(self) -> bool:
        return self.enabled and self.configured

    @property
    def api_base_v2(self) -> str:
        base = self.api_base.rstrip("/")
        return base if base.endswith("/api-v2") else base + "/api-v2"

    @property
    def missing_required(self) -> list[str]:
        req = {
            "YOUGILE_API_KEY": self.api_key,
            "YOUGILE_COLUMN_TODO_ID": self.column_todo_id,
        }
        return [name for name, value in req.items() if not value]

    def column_for(self, status: str) -> str:
        attr = STATUS_TO_COLUMN_ATTR.get(status)
        return getattr(self, attr) if attr else ""

    @classmethod
    def from_settings(cls, settings: Any) -> YouGileConfig:
        return cls(
            enabled=bool(getattr(settings, "yougile_enabled", False)),
            api_base=getattr(settings, "yougile_api_base_url", "https://ru.yougile.com"),
            api_key=getattr(settings, "yougile_api_key", "") or "",
            company_id=getattr(settings, "yougile_company_id", "") or "",
            project_id=getattr(settings, "yougile_project_id", "") or "",
            board_id=getattr(settings, "yougile_board_id", "") or "",
            column_todo_id=getattr(settings, "yougile_column_todo_id", "") or "",
            column_in_progress_id=getattr(settings, "yougile_column_in_progress_id", "") or "",
            column_done_id=getattr(settings, "yougile_column_done_id", "") or "",
            user_map=_parse_user_map(getattr(settings, "yougile_user_map", "") or ""),
        )


def _parse_user_map(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        logger.warning("YOUGILE_USER_MAP is not a JSON object — ignoring")
    except json.JSONDecodeError:
        logger.warning("YOUGILE_USER_MAP is not valid JSON — ignoring")
    return {}


@dataclass
class YouGileHealth:
    ok: bool
    status: str  # connected | error | disabled
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncResult:
    """Outcome of a YouGile create/move attempt."""

    yougile_status: str  # disabled | pending | synced | error
    yougile_task_id: str = ""
    yougile_error: str = ""
