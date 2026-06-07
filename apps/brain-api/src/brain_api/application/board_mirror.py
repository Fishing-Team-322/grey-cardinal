"""Operational mirror between local tasks and the selected YouGile board."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain_api.config import Settings
from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskStatus
from brain_api.infrastructure.board.yougile import mark_outbound
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher
from brain_api.integrations.yougile import YouGileClient, YouGileMappingRepo
from grey_cardinal_contracts import BoardCardResult, BoardProvider


@dataclass
class ImportSummary:
    imported_tasks: int = 0
    updated_tasks: int = 0
    skipped_tasks: int = 0
    columns: int = 0
    errors: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {
            "imported_tasks": self.imported_tasks,
            "updated_tasks": self.updated_tasks,
            "skipped_tasks": self.skipped_tasks,
            "columns": self.columns,
            "errors": self.errors,
        }


@dataclass
class SyncResult:
    ok: bool
    sync_status: str
    external_task_id: str | None = None
    error: str | None = None


class BoardMirrorService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        client_factory: Callable[[str], YouGileClient] | None = None,
    ) -> None:
        self._sf = session_factory
        self._settings = settings
        self._cipher = SecretCipher(settings.board_creds_encryption_key or "dev-key")
        self._client_factory = client_factory

    async def import_selected_board(self, team_id: UUID) -> ImportSummary:
        summary = ImportSummary()
        async with self._sf() as session:
            context = await self._context(session, team_id)
            summary.columns = len(context["columns"])
            for column in context["columns"]:
                try:
                    tasks = await context["client"].list_tasks(column_id=column.external_id)
                except Exception as exc:  # noqa: BLE001
                    summary.errors.append(f"{column.name}: {exc}")
                    continue
                for payload in tasks:
                    await self._import_task(
                        session,
                        team_id,
                        context["board"],
                        column,
                        payload,
                        summary,
                    )
            self._event(
                session,
                team_id,
                direction="inbound",
                action="import_board",
                status="ok" if not summary.errors else "error",
                payload=summary.payload(),
                error="; ".join(summary.errors) or None,
            )
            await session.commit()
        return summary

    async def create_external_task(self, task_id: UUID) -> SyncResult:
        async with self._sf() as session:
            task = await session.get(m.TaskModel, task_id)
            if task is None or task.team_id is None:
                return SyncResult(False, "error", error="task_not_found")
            try:
                context = await self._context(session, task.team_id)
            except RuntimeError as exc:
                link = await self._link_for_task(session, task.id)
                if link is None:
                    link = m.ExternalTaskLinkModel(
                        team_id=task.team_id,
                        task_id=task.id,
                        provider="yougile",
                        external_board_id="",
                        external_task_id=f"pending:{task.id}",
                    )
                    session.add(link)
                link.sync_status = "local_only"
                link.last_error = str(exc)
                await session.commit()
                return SyncResult(False, "local_only", link.external_task_id, str(exc))
            target = context["status_columns"].get(task.status) or context[
                "status_columns"
            ].get("todo")
            if target is None:
                return await self._mark_create_error(
                    session, task, context["board"], "no_mapped_todo_column"
                )
            link = await self._link_for_task(session, task.id)
            if link is None:
                link = m.ExternalTaskLinkModel(
                    team_id=task.team_id,
                    task_id=task.id,
                    provider="yougile",
                    external_board_id=context["board"].external_id,
                    external_task_id=f"pending:{task.id}",
                    sync_status="pending_create",
                )
                session.add(link)
                await session.flush()
            else:
                link.sync_status = "pending_create"
                link.last_error = None
            try:
                data = await context["client"].create_task(
                    f"{task.public_id} {task.title}".strip(),
                    target.external_id,
                    description=task.description,
                    assigned=await self._yougile_assignee(session, task.team_id, task.assignee_id),
                    deadline=_deadline(task.deadline),
                )
                external_id = str(data.get("id") or "")
                link.external_task_id = external_id
                link.external_column_id = target.external_id
                link.raw_payload = data
                link.sync_status = "synced"
                link.last_synced_at = datetime.now(UTC)
                mark_outbound(task.team_id, external_id)
                await YouGileMappingRepo(session, task.team_id).upsert(
                    "task",
                    external_id,
                    local_id=task.id,
                    payload=data,
                )
                self._event(
                    session,
                    task.team_id,
                    task_id=task.id,
                    link_id=link.id,
                    direction="outbound",
                    action="create",
                    status="synced",
                    payload=data,
                )
                await session.commit()
                return SyncResult(True, "synced", external_id)
            except Exception as exc:  # noqa: BLE001
                link.sync_status = "error"
                link.last_error = str(exc)
                self._event(
                    session,
                    task.team_id,
                    task_id=task.id,
                    link_id=link.id,
                    direction="outbound",
                    action="create",
                    status="error",
                    error=str(exc),
                )
                await session.commit()
                return SyncResult(False, "error", error=str(exc))

    async def move_task(self, task_id: UUID, status: TaskStatus) -> SyncResult:
        async with self._sf() as session:
            task = await session.get(m.TaskModel, task_id)
            if task is None or task.team_id is None:
                return SyncResult(False, "error", error="task_not_found")
            task.status = status.value
            task.last_status_update_at = datetime.now(UTC)
            if status == TaskStatus.done:
                task.completed_at = task.last_status_update_at
            link = await self._link_for_task(session, task.id)
            if link is None or link.external_task_id.startswith("pending:"):
                await session.commit()
                return await self.create_external_task(task.id)
            context = await self._context(session, task.team_id)
            target = context["status_columns"].get(status.value)
            if target is None:
                return await self._mark_link_error(
                    session, task, link, f"no_mapped_column:{status.value}"
                )
            link.sync_status = "pending_update"
            try:
                fields: dict[str, Any] = {"columnId": target.external_id}
                if status == TaskStatus.done:
                    fields["completed"] = True
                data = await context["client"].update_task(link.external_task_id, **fields)
                link.external_column_id = target.external_id
                link.sync_status = "synced"
                link.last_error = None
                link.last_synced_at = datetime.now(UTC)
                link.raw_payload = {**(link.raw_payload or {}), **data, **fields}
                mark_outbound(task.team_id, link.external_task_id)
                await YouGileMappingRepo(session, task.team_id).upsert(
                    "task",
                    link.external_task_id,
                    local_id=task.id,
                    payload=link.raw_payload,
                )
                self._event(
                    session,
                    task.team_id,
                    task_id=task.id,
                    link_id=link.id,
                    direction="outbound",
                    action="move",
                    status="synced",
                    payload=fields,
                )
                await session.commit()
                return SyncResult(True, "synced", link.external_task_id)
            except Exception as exc:  # noqa: BLE001
                return await self._mark_link_error(session, task, link, str(exc))

    async def sync_task_fields(self, task_id: UUID) -> SyncResult:
        async with self._sf() as session:
            task = await session.get(m.TaskModel, task_id)
            if task is None or task.team_id is None:
                return SyncResult(False, "error", error="task_not_found")
            link = await self._link_for_task(session, task.id)
            if link is None or link.external_task_id.startswith("pending:"):
                await session.commit()
                return await self.create_external_task(task.id)
            try:
                context = await self._context(session, task.team_id)
            except RuntimeError as exc:
                link.sync_status = "local_only"
                link.last_error = str(exc)
                await session.commit()
                return SyncResult(False, "local_only", link.external_task_id, str(exc))
            target = context["status_columns"].get(task.status)
            if target is None:
                return await self._mark_link_error(
                    session, task, link, f"no_mapped_column:{task.status}"
                )
            fields: dict[str, Any] = {
                "title": f"{task.public_id} {task.title}".strip(),
                "description": task.description,
                "columnId": target.external_id,
                "assigned": await self._yougile_assignee(
                    session, task.team_id, task.assignee_id
                ),
                "deadline": _deadline(task.deadline),
            }
            if task.status == TaskStatus.done.value:
                fields["completed"] = True
            link.sync_status = "pending_update"
            try:
                data = await context["client"].update_task(link.external_task_id, **fields)
                link.external_board_id = context["board"].external_id
                link.external_column_id = target.external_id
                link.sync_status = "synced"
                link.last_error = None
                link.last_synced_at = datetime.now(UTC)
                link.raw_payload = {**(link.raw_payload or {}), **data, **fields}
                mark_outbound(task.team_id, link.external_task_id)
                await YouGileMappingRepo(session, task.team_id).upsert(
                    "task",
                    link.external_task_id,
                    local_id=task.id,
                    payload=link.raw_payload,
                )
                self._event(
                    session,
                    task.team_id,
                    task_id=task.id,
                    link_id=link.id,
                    direction="outbound",
                    action="update",
                    status="synced",
                    payload=fields,
                )
                await session.commit()
                return SyncResult(True, "synced", link.external_task_id)
            except Exception as exc:  # noqa: BLE001
                return await self._mark_link_error(session, task, link, str(exc))

    async def close_task(self, task_id: UUID) -> SyncResult:
        return await self.move_task(task_id, TaskStatus.done)

    async def sync_inbound(self, team_id: UUID) -> dict[str, Any]:
        return (await self.import_selected_board(team_id)).payload()

    async def sync_outbound(self, team_id: UUID) -> dict[str, Any]:
        async with self._sf() as session:
            links = list(
                await session.scalars(
                    select(m.ExternalTaskLinkModel).where(
                        m.ExternalTaskLinkModel.team_id == team_id,
                        m.ExternalTaskLinkModel.sync_status.in_(
                            ["local_only", "pending_create", "pending_update", "error"]
                        ),
                    )
                )
            )
        results = [
            (
                await self.create_external_task(link.task_id)
                if link.external_task_id.startswith("pending:")
                else await self.sync_task_fields(link.task_id)
            )
            for link in links
        ]
        return {
            "processed": len(results),
            "synced": sum(result.ok for result in results),
            "errors": [result.error for result in results if result.error],
        }

    async def resolve_conflict(self, link_id: UUID, strategy: str) -> SyncResult:
        async with self._sf() as session:
            link = await session.get(m.ExternalTaskLinkModel, link_id)
            if link is None:
                return SyncResult(False, "error", error="link_not_found")
            if strategy == "external":
                payload = link.raw_payload or {}
                task = await session.get(m.TaskModel, link.task_id)
                if task is not None:
                    task.title = str(payload.get("title") or task.title)
                link.sync_status = "synced"
                link.last_error = None
                await session.commit()
                return SyncResult(True, "synced", link.external_task_id)
        return await self.create_external_task(link.task_id)

    async def task_id_for_external(self, external_task_id: str) -> UUID | None:
        async with self._sf() as session:
            return await session.scalar(
                select(m.ExternalTaskLinkModel.task_id).where(
                    m.ExternalTaskLinkModel.provider == "yougile",
                    m.ExternalTaskLinkModel.external_task_id == external_task_id,
                )
            )

    async def _context(self, session: AsyncSession, team_id: UUID) -> dict[str, Any]:
        team = await session.get(m.TeamModel, team_id)
        if team is None or not team.board_credentials_encrypted:
            raise RuntimeError("YouGile is not connected")
        board = await session.scalar(
            select(m.YouGileBoardModel).where(
                m.YouGileBoardModel.team_id == team_id,
                m.YouGileBoardModel.is_selected.is_(True),
            )
        )
        if board is None:
            raise RuntimeError("YouGile board is not selected")
        columns = list(
            await session.scalars(
                select(m.YouGileColumnModel)
                .where(m.YouGileColumnModel.board_id == board.id)
                .order_by(m.YouGileColumnModel.position)
            )
        )
        credentials = json.loads(
            self._cipher.decrypt_text(team.board_credentials_encrypted) or "{}"
        )
        client = (
            self._client_factory(credentials.get("api_key", ""))
            if self._client_factory
            else YouGileClient(
                credentials.get("api_key", ""),
                base_url=self._settings.yougile_api_base_url,
                rate_per_minute=self._settings.yougile_rate_limit_per_minute,
            )
        )
        return {
            "team": team,
            "board": board,
            "columns": columns,
            "status_columns": {
                column.mapped_status: column for column in columns if column.mapped_status
            },
            "client": client,
        }

    async def _import_task(
        self,
        session: AsyncSession,
        team_id: UUID,
        board: m.YouGileBoardModel,
        column: m.YouGileColumnModel,
        payload: dict[str, Any],
        summary: ImportSummary,
    ) -> None:
        external_id = str(payload.get("id") or "")
        if not external_id:
            summary.skipped_tasks += 1
            return
        link = await session.scalar(
            select(m.ExternalTaskLinkModel).where(
                m.ExternalTaskLinkModel.provider == "yougile",
                m.ExternalTaskLinkModel.external_task_id == external_id,
            )
        )
        if link is not None and link.team_id != team_id:
            summary.skipped_tasks += 1
            summary.errors.append(
                f"{external_id}: external task is already linked to another team"
            )
            return
        status = column.mapped_status or "todo"
        title = _clean_external_title(str(payload.get("title") or "Без названия"))
        assignee_id = await self._local_assignee(session, team_id, payload.get("assigned") or [])
        deadline = _parse_deadline(payload.get("deadline"))
        now = datetime.now(UTC)
        if link is None:
            seq = int(await session.scalar(select(func.max(m.TaskModel.seq))) or 0) + 1
            task = m.TaskModel(
                seq=seq,
                public_id=f"GC-{seq}",
                team_id=team_id,
                title=title,
                description=payload.get("description"),
                status=status,
                priority="medium",
                assignee_id=assignee_id,
                assignee_text=None,
                deadline=deadline,
                source="yougile_import",
            )
            session.add(task)
            await session.flush()
            link = m.ExternalTaskLinkModel(
                team_id=team_id,
                task_id=task.id,
                provider="yougile",
                external_board_id=board.external_id,
                external_column_id=column.external_id,
                external_task_id=external_id,
                last_synced_at=now,
                sync_status="synced",
                raw_payload=payload,
            )
            session.add(link)
            summary.imported_tasks += 1
        else:
            existing_task = await session.get(m.TaskModel, link.task_id)
            if existing_task is None:
                summary.skipped_tasks += 1
                return
            task = existing_task
            task.title = title
            task.description = payload.get("description")
            task.status = status
            task.assignee_id = assignee_id
            task.deadline = deadline
            link.external_board_id = board.external_id
            link.external_column_id = column.external_id
            link.last_synced_at = now
            link.sync_status = "synced"
            link.last_error = None
            link.raw_payload = payload
            summary.updated_tasks += 1
        await session.flush()

    async def _link_for_task(
        self, session: AsyncSession, task_id: UUID
    ) -> m.ExternalTaskLinkModel | None:
        return await session.scalar(
            select(m.ExternalTaskLinkModel).where(
                m.ExternalTaskLinkModel.task_id == task_id,
                m.ExternalTaskLinkModel.provider == "yougile",
            )
        )

    async def _yougile_assignee(
        self, session: AsyncSession, team_id: UUID, user_id: UUID | None
    ) -> list[str] | None:
        if user_id is None:
            return None
        external_id = await session.scalar(
            select(m.YouGileMappingModel.yougile_id).where(
                m.YouGileMappingModel.team_id == team_id,
                m.YouGileMappingModel.entity_type == "user",
                m.YouGileMappingModel.local_id == user_id,
            )
        )
        return [external_id] if external_id else None

    async def _local_assignee(
        self, session: AsyncSession, team_id: UUID, external_ids: list[str]
    ) -> UUID | None:
        if not external_ids:
            return None
        return await session.scalar(
            select(m.YouGileMappingModel.local_id).where(
                m.YouGileMappingModel.team_id == team_id,
                m.YouGileMappingModel.entity_type == "user",
                m.YouGileMappingModel.yougile_id.in_([str(item) for item in external_ids]),
                m.YouGileMappingModel.local_id.is_not(None),
            )
        )

    async def _mark_create_error(
        self,
        session: AsyncSession,
        task: m.TaskModel,
        board: m.YouGileBoardModel,
        error: str,
    ) -> SyncResult:
        link = await self._link_for_task(session, task.id)
        if link is None:
            link = m.ExternalTaskLinkModel(
                team_id=task.team_id,
                task_id=task.id,
                provider="yougile",
                external_board_id=board.external_id,
                external_task_id=f"pending:{task.id}",
                sync_status="error",
                last_error=error,
            )
            session.add(link)
        else:
            link.sync_status = "error"
            link.last_error = error
        await session.commit()
        return SyncResult(False, "error", error=error)

    async def _mark_link_error(
        self,
        session: AsyncSession,
        task: m.TaskModel,
        link: m.ExternalTaskLinkModel,
        error: str,
    ) -> SyncResult:
        assert task.team_id is not None
        link.sync_status = "error"
        link.last_error = error
        self._event(
            session,
            task.team_id,
            task_id=task.id,
            link_id=link.id,
            direction="outbound",
            action="move",
            status="error",
            error=error,
        )
        await session.commit()
        return SyncResult(False, "error", link.external_task_id, error)

    @staticmethod
    def _event(
        session: AsyncSession,
        team_id: UUID,
        *,
        direction: str,
        action: str,
        status: str,
        task_id: UUID | None = None,
        link_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        session.add(
            m.SyncEventModel(
                team_id=team_id,
                task_id=task_id,
                link_id=link_id,
                provider="yougile",
                direction=direction,
                action=action,
                entity_type="task",
                entity_id=task_id,
                status=status,
                message=error,
                payload=payload,
                error=error,
            )
        )


class BoardMirrorGateway:
    """BoardGateway compatibility wrapper backed by BoardMirrorService."""

    def __init__(self, mirror: BoardMirrorService) -> None:
        self._mirror = mirror

    async def create_card(self, task: Task) -> BoardCardResult:
        result = await self._mirror.create_external_task(task.id)
        return BoardCardResult(
            provider=BoardProvider.yougile,
            external_card_id=result.external_task_id or "",
            external_payload={
                "sync_status": result.sync_status,
                "error": result.error,
            },
        )

    async def move_card(self, external_card_id: str, status: TaskStatus) -> None:
        task_id = await self._mirror.task_id_for_external(external_card_id)
        if task_id is not None:
            await self._mirror.move_task(task_id, status)

    async def close_card(self, external_card_id: str) -> None:
        task_id = await self._mirror.task_id_for_external(external_card_id)
        if task_id is not None:
            await self._mirror.close_task(task_id)

    async def add_comment(self, external_card_id: str, text: str) -> None:
        return None


def _clean_external_title(title: str) -> str:
    parts = title.split(maxsplit=1)
    if len(parts) == 2 and parts[0].upper().startswith("GC-"):
        return parts[1]
    return title


def _deadline(value: datetime | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"deadline": int(value.timestamp() * 1000), "withTime": True}


def _parse_deadline(value: Any) -> datetime | None:
    if not isinstance(value, dict) or not value.get("deadline"):
        return None
    return datetime.fromtimestamp(float(value["deadline"]) / 1000, tz=UTC)
