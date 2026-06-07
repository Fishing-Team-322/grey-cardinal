"""Per-team YouGile board adapter (outbound sync).

Conforms to the BoardGateway protocol so existing use-cases (ConfirmTask, status
flow) are unchanged. external_card_id IS the YouGile task id. In addition to the
BoardCardModel the caller persists, this records yougile_mappings(task) so
discovery and inbound webhooks share one task map, and writes yougile_sync_log.

Resilience: a YouGileAuthError (expired key) does NOT raise — the local task is
kept, the error is logged, and the team is flagged so the UI can show a
"reconnect" banner. Loop protection suppresses the webhook echo of our own push.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskStatus
from brain_api.infrastructure.db import models as m
from brain_api.integrations.yougile import (
    YouGileAuthError,
    YouGileClient,
    YouGileError,
    YouGileMappingRepo,
)
from grey_cardinal_contracts import BoardCardResult, BoardProvider

logger = logging.getLogger(__name__)

# Status -> board_config.default_column_ids key.
_STATUS_KEY = {
    TaskStatus.todo: "todo",
    TaskStatus.in_progress: "in_progress",
    TaskStatus.done: "done",
}

# Loop protection: remember our own outbound writes briefly so the resulting
# inbound webhook can be ignored. (team_id, yougile_id) -> expiry monotonic.
_LOOP_GUARD: dict[tuple[str, str], float] = {}
_LOOP_TTL = 5.0


def mark_outbound(team_id: UUID, yougile_id: str) -> None:
    _LOOP_GUARD[(str(team_id), str(yougile_id))] = time.monotonic() + _LOOP_TTL


def was_recent_outbound(team_id: UUID, yougile_id: str) -> bool:
    key = (str(team_id), str(yougile_id))
    exp = _LOOP_GUARD.get(key)
    now = time.monotonic()
    if exp is None:
        return False
    if exp < now:
        _LOOP_GUARD.pop(key, None)
        return False
    return True


class YouGileBoardAdapter:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        team_id: UUID,
        client: YouGileClient,
        default_columns: dict[str, str],
    ) -> None:
        self._sf = session_factory
        self._team_id = team_id
        self._client = client
        self._cols = default_columns or {}

    # ── BoardGateway protocol ────────────────────────────────────────────────
    async def create_card(self, task: Task) -> BoardCardResult:
        column_id = self._cols.get("todo")
        if not column_id:
            return await self._degraded(task, "no default 'todo' column configured")
        assigned = await self._resolve_assignee(task.assignee_id)
        title = f"{task.public_id} {task.title}".strip()
        try:
            data = await self._client.create_task(
                title,
                column_id,
                description=_description(task),
                assigned=assigned or None,
                deadline=_deadline(task.deadline),
            )
        except YouGileAuthError as exc:
            await self._flag_auth_error()
            await self._log(event="task-pushed", error=f"auth:{exc.status}", local_id=task.id)
            return BoardCardResult(
                provider=BoardProvider.yougile,
                external_card_id="",
                external_payload={"error": "auth"},
            )
        except YouGileError as exc:
            await self._log(event="task-pushed", error=str(exc), local_id=task.id)
            return BoardCardResult(
                provider=BoardProvider.yougile,
                external_card_id="",
                external_payload={"error": "sync"},
            )
        yg_id = str(data.get("id") or "")
        mark_outbound(self._team_id, yg_id)
        await self._record_task(local_id=task.id, yougile_id=yg_id, payload=data)
        return BoardCardResult(
            provider=BoardProvider.yougile, external_card_id=yg_id, external_payload=data
        )

    async def move_card(self, external_card_id: str, status: TaskStatus) -> None:
        if not external_card_id:
            return
        target = self._cols.get(_STATUS_KEY.get(status, ""))
        if not target:
            logger.info("YouGile: no column for status %s — skip move", status.value)
            return
        await self._update(external_card_id, {"columnId": target}, event="task-moved")

    async def close_card(self, external_card_id: str) -> None:
        if not external_card_id:
            return
        fields: dict = {"completed": True}
        done = self._cols.get("done")
        if done:
            fields["columnId"] = done
        await self._update(external_card_id, fields, event="task-closed")

    async def add_comment(self, external_card_id: str, text: str) -> None:
        if not external_card_id:
            return
        try:
            await self._client.create_chat_message(external_card_id, text)
        except YouGileAuthError as exc:
            await self._flag_auth_error()
            await self._log(
                event="comment-pushed",
                yougile_id=external_card_id,
                error=f"auth:{exc.status}",
            )
            return
        except YouGileError as exc:
            await self._log(
                event="comment-pushed",
                yougile_id=external_card_id,
                error=str(exc),
            )
            return
        mark_outbound(self._team_id, external_card_id)
        await self._log(event="comment-pushed", yougile_id=external_card_id)

    # ── internals ─────────────────────────────────────────────────────────────
    async def _update(self, yg_id: str, fields: dict, *, event: str) -> None:
        try:
            await self._client.update_task(yg_id, **fields)
        except YouGileAuthError as exc:
            await self._flag_auth_error()
            await self._log(event=event, yougile_id=yg_id, error=f"auth:{exc.status}")
            return
        except YouGileError as exc:
            await self._log(event=event, yougile_id=yg_id, error=str(exc))
            return
        mark_outbound(self._team_id, yg_id)
        await self._log(event=event, yougile_id=yg_id)

    async def _resolve_assignee(self, assignee_id: UUID | None) -> list[str]:
        if assignee_id is None:
            return []
        async with self._sf() as session:
            repo = YouGileMappingRepo(session, self._team_id)
            row = await repo.find_by_local("user", assignee_id)
            return [row.yougile_id] if row else []

    async def _record_task(self, *, local_id: UUID, yougile_id: str, payload: dict) -> None:
        async with self._sf() as session:
            repo = YouGileMappingRepo(session, self._team_id)
            await repo.upsert("task", yougile_id, local_id=local_id, payload=payload)
            repo.log(
                direction="outbound",
                event="task-pushed",
                entity_type="task",
                yougile_id=yougile_id,
                local_id=local_id,
            )
            await session.commit()

    async def _log(
        self,
        *,
        event: str,
        yougile_id: str | None = None,
        local_id: UUID | None = None,
        error: str | None = None,
    ) -> None:
        async with self._sf() as session:
            YouGileMappingRepo(session, self._team_id).log(
                direction="outbound",
                event=event,
                entity_type="task",
                yougile_id=yougile_id,
                local_id=local_id,
                error=error,
            )
            await session.commit()

    async def _flag_auth_error(self) -> None:
        async with self._sf() as session:
            team = await session.get(m.TeamModel, self._team_id)
            if team is not None:
                config = dict(team.board_config or {})
                config["integration_status"] = "auth_error"
                team.board_provider = "mock"
                team.board_config = config
                session.add(team)
                await session.commit()

    async def _degraded(self, task: Task, reason: str) -> BoardCardResult:
        await self._log(event="task-pushed", local_id=task.id, error=reason)
        return BoardCardResult(
            provider=BoardProvider.yougile, external_card_id="", external_payload={"error": reason}
        )


def _description(task: Task) -> str:
    parts = []
    if task.assignee_text:
        parts.append(f"Ответственный: {task.assignee_text}")
    if task.deadline:
        parts.append(f"Дедлайн: {task.deadline.isoformat()}")
    parts.append(f"Источник: {task.source.value}")
    parts.append("Создано Grey Cardinal")
    return "\n".join(parts)


def _deadline(value: datetime | None) -> dict | None:
    if value is None:
        return None
    return {
        "deadline": int(value.timestamp() * 1000),
        "withTime": True,
    }
