"""Agentic PM read models and full YouGile sync use-cases."""
# ruff: noqa: E501

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application.task_numbering import next_task_public_id
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher
from brain_api.integrations.yougile import YouGileClient

TERMINAL_STATUSES = {"done", "cancelled"}
ACTIVE_STATUSES = {"todo", "proposed", "new", "in_progress", "blocked", "review"}
STATUS_ALIASES = {
    "backlog": ("backlog", "бэклог"),
    "todo": ("todo", "to do", "к выполнению", "сделать", "новые"),
    "in_progress": ("in progress", "doing", "в работе", "делается"),
    "blocked": ("blocked", "block", "заблокировано", "стоп"),
    "review": ("review", "ревью", "проверка"),
    "done": ("done", "completed", "готово", "закрыто", "сделано"),
}


class YouGileFullSyncService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        team_id: UUID,
        cipher: SecretCipher,
        api_base_url: str,
        client: YouGileClient | None = None,
    ) -> None:
        self.session = session
        self.team_id = team_id
        self.cipher = cipher
        self.api_base_url = api_base_url
        self._client = client

    async def client(self) -> YouGileClient:
        if self._client is not None:
            return self._client
        connection = await self.active_connection()
        raw = self.cipher.decrypt_text(connection.credentials_encrypted) or "{}"
        api_key = json.loads(raw).get("api_key", "")
        self._client = YouGileClient(api_key, base_url=self.api_base_url)
        return self._client

    async def active_connection(self) -> m.YouGileConnectionModel:
        connection = await self.session.scalar(
            select(m.YouGileConnectionModel)
            .where(
                m.YouGileConnectionModel.team_id == self.team_id,
                m.YouGileConnectionModel.provider == "yougile",
            )
            .order_by(m.YouGileConnectionModel.created_at.desc())
        )
        if connection is not None:
            return connection

        team = await self.session.get(m.TeamModel, self.team_id)
        if team is None or not team.board_credentials_encrypted:
            raise ValueError("YouGile is not connected")
        connection = m.YouGileConnectionModel(
            id=uuid4(),
            team_id=self.team_id,
            provider="yougile",
            credentials_encrypted=team.board_credentials_encrypted,
            status="active",
            last_checked_at=datetime.now(UTC),
        )
        self.session.add(connection)
        await self.session.flush()
        return connection

    async def check_connection(self) -> dict[str, Any]:
        connection = await self.active_connection()
        try:
            health = await (await self.client()).health()
        except Exception as exc:  # noqa: BLE001 - surfaced as connection status
            connection.status = "error"
            connection.last_error = str(exc)
            connection.last_checked_at = datetime.now(UTC)
            self.session.add(connection)
            await self._sync_event(
                "inbound", "connection", None, "error", message=str(exc)
            )
            await self.session.commit()
            return {"connected": False, "status": "error", "last_error": str(exc)}
        connection.status = "active"
        connection.last_error = None
        connection.last_checked_at = datetime.now(UTC)
        self.session.add(connection)
        await self.session.commit()
        return {"connected": True, "status": "active", "health": health}

    async def refresh_catalog(self) -> dict[str, int]:
        connection = await self.active_connection()
        client = await self.client()
        now = datetime.now(UTC)
        stats = {"workspaces": 0, "projects": 0, "boards": 0, "columns": 0, "users": 0}

        workspaces = await _maybe_call(client, "list_workspaces", [])
        for workspace in workspaces:
            await self._upsert_workspace(connection.id, workspace, now)
        stats["workspaces"] = len(workspaces)

        projects = await client.list_projects()
        project_by_external: dict[str, m.YouGileProjectModel] = {}
        for project in projects:
            row = await self._upsert_project(connection.id, project, now)
            project_by_external[str(project.get("id"))] = row
        stats["projects"] = len(projects)

        for project in projects:
            project_external_id = str(project.get("id"))
            boards = await client.list_boards(project_id=project_external_id)
            stats["boards"] += len(boards)
            for board in boards:
                board_row = await self._upsert_board(
                    connection.id,
                    _project_id(project_by_external.get(project_external_id)),
                    board,
                    now,
                )
                columns = await client.list_columns(board_id=str(board.get("id")))
                stats["columns"] += len(columns)
                for index, column in enumerate(columns):
                    await self._upsert_column(board_row.id, column, now, index)

        users = await _maybe_call(client, "list_users", [])
        for user in users:
            await self._upsert_mapping("user", str(user.get("id")), payload=user)
        stats["users"] = len(users)
        await self._sync_event("inbound", "catalog", None, "success", payload=stats)
        await self.session.commit()
        return stats

    async def select_board(
        self,
        board_id: str,
        mapping: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        board = await self._board_by_any_id(board_id)
        if board is None:
            await self.refresh_catalog()
            board = await self._board_by_any_id(board_id)
        if board is None:
            raise ValueError("YouGile board not found")
        await self.session.execute(
            update(m.YouGileBoardModel)
            .where(m.YouGileBoardModel.team_id == self.team_id)
            .values(is_selected=False)
        )
        board.is_selected = True
        self.session.add(board)

        if mapping:
            columns = (
                (
                    await self.session.execute(
                        select(m.YouGileColumnModel).where(
                            m.YouGileColumnModel.board_id == board.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_external = {col.external_id: col for col in columns}
            by_local = {str(col.id): col for col in columns}
            for status_name, column_ref in mapping.items():
                column = by_external.get(column_ref) or by_local.get(column_ref)
                if column is not None:
                    column.mapped_status = status_name
                    self.session.add(column)
        else:
            await self._auto_map_columns(board.id)
        await self._sync_event(
            "inbound",
            "board",
            board.id,
            "success",
            external_id=board.external_id,
            message="selected",
        )
        await self.session.commit()
        return _board_payload(board)

    async def import_selected_board(self) -> dict[str, Any]:
        board = await self.selected_board()
        if board is None:
            raise ValueError("No selected YouGile board")
        client = await self.client()
        now = datetime.now(UTC)
        columns = await client.list_columns(board_id=board.external_id)
        for index, column in enumerate(columns):
            await self._upsert_column(board.id, column, now, index)
        await self._auto_map_columns(board.id)

        summary: dict[str, Any] = {
            "imported_tasks": 0,
            "updated_tasks": 0,
            "skipped_tasks": 0,
            "columns": len(columns),
            "errors": [],
        }
        for column in columns:
            column_id = str(column.get("id"))
            try:
                tasks = await client.list_tasks(column_id=column_id)
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append({"column_id": column_id, "error": str(exc)})
                continue
            for payload in tasks:
                result = await self._upsert_local_task_from_yougile(board, column_id, payload)
                summary[result] += 1
        await self._sync_event("inbound", "task", board.id, "success", payload=summary)
        await self.session.commit()
        return summary

    async def sync_selected_board(self) -> dict[str, Any]:
        board = await self.selected_board()
        if board is None:
            raise ValueError("No selected YouGile board")
        inbound = await self.import_selected_board()
        outbound = await self._sync_local_changes(board)
        summary = {"inbound": inbound, "outbound": outbound}
        await self._sync_event("inbound", "task", board.id, "success", message="manual sync", payload=summary)
        await self.session.commit()
        return summary

    async def selected_board(self) -> m.YouGileBoardModel | None:
        return await self.session.scalar(
            select(m.YouGileBoardModel).where(
                m.YouGileBoardModel.team_id == self.team_id,
                m.YouGileBoardModel.is_selected.is_(True),
            )
        )

    async def _sync_local_changes(self, board: m.YouGileBoardModel) -> dict[str, int]:
        client = await self.client()
        columns = await self._columns_for_board(board.id)
        default_column = _column_for_status(columns, "todo") or (columns[0] if columns else None)
        pushed = created = errors = 0
        rows = (
            (
                await self.session.execute(
                    select(m.TaskModel, m.ExternalTaskLinkModel)
                    .outerjoin(
                        m.ExternalTaskLinkModel,
                        (m.ExternalTaskLinkModel.task_id == m.TaskModel.id)
                        & (m.ExternalTaskLinkModel.provider == "yougile"),
                    )
                    .where(m.TaskModel.team_id == self.team_id)
                )
            )
            .all()
        )
        now = datetime.now(UTC)
        for task, link in rows:
            if link and link.sync_status == "conflict":
                continue
            try:
                target_column = _column_for_status(columns, task.status) or default_column
                if link is None:
                    if target_column is None:
                        continue
                    payload = await client.create_task(
                        task.title,
                        target_column.external_id,
                        description=task.description,
                        deadline=_deadline_to_yougile(task.deadline),
                    )
                    await self._record_link(board, target_column.external_id, task, payload, now, "synced")
                    created += 1
                elif link.last_synced_at is None or _as_utc(task.updated_at) > _as_utc(link.last_synced_at):
                    fields: dict[str, Any] = {"title": task.title, "description": task.description}
                    if target_column is not None and link.external_column_id != target_column.external_id:
                        fields["columnId"] = target_column.external_id
                    if task.deadline is not None:
                        fields["deadline"] = _deadline_to_yougile(task.deadline)
                    payload = await client.update_task(link.external_task_id, **fields)
                    link.external_column_id = fields.get("columnId", link.external_column_id)
                    link.raw_payload = {**(link.raw_payload or {}), **payload}
                    link.last_synced_at = now
                    link.sync_status = "synced"
                    self.session.add(link)
                    pushed += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                if link is not None:
                    link.sync_status = "error"
                    link.last_error = str(exc)
                    self.session.add(link)
                await self._sync_event(
                    "outbound", "task", task.id, "error", external_id=link.external_task_id if link else None, message=str(exc)
                )
        return {"created": created, "pushed": pushed, "errors": errors}

    async def _upsert_local_task_from_yougile(
        self,
        board: m.YouGileBoardModel,
        column_id: str,
        payload: dict[str, Any],
    ) -> str:
        external_task_id = str(payload.get("id") or "")
        if not external_task_id:
            return "skipped_tasks"
        link = await self.session.scalar(
            select(m.ExternalTaskLinkModel).where(
                m.ExternalTaskLinkModel.provider == "yougile",
                m.ExternalTaskLinkModel.external_task_id == external_task_id,
            )
        )
        now = datetime.now(UTC)
        status_name = await self._status_for_column(board.id, column_id)
        if link is not None:
            task = await self.session.get(m.TaskModel, link.task_id)
            if task is None:
                return "skipped_tasks"
            if (
                link.last_synced_at
                and _as_utc(task.updated_at) > _as_utc(link.last_synced_at)
                and _task_differs(task, payload, status_name)
            ):
                link.sync_status = "conflict"
                link.raw_payload = payload
                self.session.add(link)
                await self._conflict_inbox(task, payload, link)
                return "skipped_tasks"
            _apply_yougile_payload(task, payload, status_name)
            link.external_board_id = board.external_id
            link.external_column_id = column_id
            link.raw_payload = payload
            link.last_synced_at = now
            link.sync_status = "synced"
            self.session.add_all([task, link])
            await self._upsert_mapping("task", external_task_id, local_id=task.id, payload=payload)
            return "updated_tasks"

        task = await self._create_task_from_payload(payload, status_name, board, column_id)
        await self._record_link(board, column_id, task, payload, now, "synced")
        await self._upsert_mapping("task", external_task_id, local_id=task.id, payload=payload)
        return "imported_tasks"

    async def _create_task_from_payload(
        self,
        payload: dict[str, Any],
        status_name: str,
        board: m.YouGileBoardModel,
        column_id: str,
    ) -> m.TaskModel:
        seq, public_id = await next_task_public_id(self.session, self.team_id)
        assignee_id, assignee_text = await self._assignee_from_payload(payload)
        task = m.TaskModel(
            id=uuid4(),
            seq=seq,
            public_id=public_id,
            team_id=self.team_id,
            title=str(payload.get("title") or "YouGile task"),
            description=payload.get("description"),
            status=status_name,
            priority=_priority_from_payload(payload),
            assignee_id=assignee_id,
            assignee_text=assignee_text,
            deadline=_deadline_from_yougile(payload.get("deadline")),
            deadline_timezone="UTC",
            source="yougile",
            source_type="yougile_board",
            source_id=board.external_id,
            source_text=str(payload.get("title") or ""),
            source_url=_yougile_task_url(payload),
            source_payload=payload,
            last_status_update_at=datetime.now(UTC),
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def _record_link(
        self,
        board: m.YouGileBoardModel,
        column_id: str,
        task: m.TaskModel,
        payload: dict[str, Any],
        synced_at: datetime,
        status_name: str,
    ) -> m.ExternalTaskLinkModel:
        link = m.ExternalTaskLinkModel(
            id=uuid4(),
            team_id=self.team_id,
            task_id=task.id,
            provider="yougile",
            external_board_id=board.external_id,
            external_column_id=column_id,
            external_task_id=str(payload.get("id")),
            external_url=_yougile_task_url(payload),
            last_synced_at=synced_at,
            sync_status=status_name,
            raw_payload=payload,
        )
        self.session.add(link)
        return link

    async def _conflict_inbox(
        self,
        task: m.TaskModel,
        payload: dict[str, Any],
        link: m.ExternalTaskLinkModel,
    ) -> None:
        self.session.add(
            m.AiInboxItemModel(
                id=uuid4(),
                team_id=self.team_id,
                item_type="sync_conflict",
                kind="sync_conflict",
                status="pending",
                source_type="yougile",
                source_id=link.external_task_id,
                source_text=str(payload.get("title") or task.title),
                reason="yougile_sync_conflict",
                raw_text=str(payload.get("title") or task.title),
                confidence=1.0,
                parsed_payload={"grey": _task_summary(task), "yougile": payload},
                semantic_payload={"grey": _task_summary(task), "yougile": payload},
                proposed_action="resolve_conflict",
                linked_task_id=task.id,
            )
        )
        await self._sync_event(
            "inbound", "task", task.id, "conflict", external_id=link.external_task_id
        )

    async def _assignee_from_payload(self, payload: dict[str, Any]) -> tuple[UUID | None, str | None]:
        assigned = payload.get("assigned") or payload.get("assignedTo") or []
        if isinstance(assigned, str):
            assigned = [assigned]
        if assigned:
            mapping = await self.session.scalar(
                select(m.YouGileMappingModel).where(
                    m.YouGileMappingModel.team_id == self.team_id,
                    m.YouGileMappingModel.entity_type == "user",
                    m.YouGileMappingModel.yougile_id == str(assigned[0]),
                )
            )
            if mapping and mapping.local_id:
                return mapping.local_id, None
            return None, str(assigned[0])
        return None, payload.get("assignee") if isinstance(payload.get("assignee"), str) else None

    async def _status_for_column(self, board_id: UUID, external_column_id: str) -> str:
        column = await self.session.scalar(
            select(m.YouGileColumnModel).where(
                m.YouGileColumnModel.board_id == board_id,
                m.YouGileColumnModel.external_id == external_column_id,
            )
        )
        return column.mapped_status if column and column.mapped_status else "todo"

    async def _columns_for_board(self, board_id: UUID) -> list[m.YouGileColumnModel]:
        return list(
            (
                await self.session.execute(
                    select(m.YouGileColumnModel)
                    .where(m.YouGileColumnModel.board_id == board_id)
                    .order_by(m.YouGileColumnModel.position, m.YouGileColumnModel.name)
                )
            )
            .scalars()
            .all()
        )

    async def _auto_map_columns(self, board_id: UUID) -> None:
        columns = await self._columns_for_board(board_id)
        used: set[str] = set()
        for column in columns:
            lowered = column.name.strip().lower()
            for status_name, aliases in STATUS_ALIASES.items():
                if status_name in used:
                    continue
                if lowered in aliases or any(alias in lowered for alias in aliases):
                    column.mapped_status = status_name
                    used.add(status_name)
                    self.session.add(column)
                    break
        fallback = ["backlog", "todo", "in_progress", "blocked", "review", "done"]
        for column, status_name in zip(
            [col for col in columns if not col.mapped_status],
            [item for item in fallback if item not in used],
            strict=False,
        ):
            column.mapped_status = status_name
            self.session.add(column)

    async def _board_by_any_id(self, board_id: str) -> m.YouGileBoardModel | None:
        try:
            as_uuid = UUID(board_id)
        except ValueError:
            as_uuid = None
        predicate = (
            or_(m.YouGileBoardModel.external_id == board_id, m.YouGileBoardModel.id == as_uuid)
            if as_uuid
            else m.YouGileBoardModel.external_id == board_id
        )
        return await self.session.scalar(
            select(m.YouGileBoardModel).where(
                m.YouGileBoardModel.team_id == self.team_id,
                predicate,
            )
        )

    async def _upsert_workspace(
        self, connection_id: UUID, payload: dict[str, Any], synced_at: datetime
    ) -> m.YouGileWorkspaceModel:
        external_id = str(payload.get("id") or payload.get("companyId") or "")
        row = await self.session.scalar(
            select(m.YouGileWorkspaceModel).where(
                m.YouGileWorkspaceModel.connection_id == connection_id,
                m.YouGileWorkspaceModel.external_id == external_id,
            )
        )
        if row is None:
            row = m.YouGileWorkspaceModel(id=uuid4(), connection_id=connection_id, external_id=external_id)
        row.name = _name(payload)
        row.raw_payload = payload
        row.synced_at = synced_at
        self.session.add(row)
        return row

    async def _upsert_project(
        self, connection_id: UUID, payload: dict[str, Any], synced_at: datetime
    ) -> m.YouGileProjectModel:
        external_id = str(payload.get("id") or "")
        row = await self.session.scalar(
            select(m.YouGileProjectModel).where(
                m.YouGileProjectModel.connection_id == connection_id,
                m.YouGileProjectModel.external_id == external_id,
            )
        )
        if row is None:
            row = m.YouGileProjectModel(id=uuid4(), connection_id=connection_id, external_id=external_id)
        row.name = _name(payload)
        row.raw_payload = payload
        row.synced_at = synced_at
        self.session.add(row)
        await self._upsert_mapping("project", external_id, payload=payload)
        return row

    async def _upsert_board(
        self,
        connection_id: UUID,
        project_id: UUID | None,
        payload: dict[str, Any],
        synced_at: datetime,
    ) -> m.YouGileBoardModel:
        external_id = str(payload.get("id") or "")
        row = await self.session.scalar(
            select(m.YouGileBoardModel).where(
                m.YouGileBoardModel.connection_id == connection_id,
                m.YouGileBoardModel.external_id == external_id,
            )
        )
        if row is None:
            row = m.YouGileBoardModel(
                id=uuid4(),
                team_id=self.team_id,
                connection_id=connection_id,
                external_id=external_id,
                is_selected=False,
            )
        row.project_id = project_id
        row.name = _name(payload)
        row.raw_payload = payload
        row.synced_at = synced_at
        self.session.add(row)
        await self._upsert_mapping("board", external_id, payload=payload)
        return row

    async def _upsert_column(
        self,
        board_id: UUID,
        payload: dict[str, Any],
        synced_at: datetime,
        position: int | None,
    ) -> m.YouGileColumnModel:
        external_id = str(payload.get("id") or "")
        row = await self.session.scalar(
            select(m.YouGileColumnModel).where(
                m.YouGileColumnModel.board_id == board_id,
                m.YouGileColumnModel.external_id == external_id,
            )
        )
        if row is None:
            row = m.YouGileColumnModel(id=uuid4(), board_id=board_id, external_id=external_id)
        row.name = _name(payload)
        row.position = position or 0
        row.raw_payload = payload
        row.synced_at = synced_at
        self.session.add(row)
        await self._upsert_mapping("column", external_id, payload=payload)
        return row

    async def _upsert_mapping(
        self,
        entity_type: str,
        external_id: str,
        *,
        local_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        mapping = await self.session.scalar(
            select(m.YouGileMappingModel).where(
                m.YouGileMappingModel.team_id == self.team_id,
                m.YouGileMappingModel.entity_type == entity_type,
                m.YouGileMappingModel.yougile_id == external_id,
            )
        )
        if mapping is None:
            mapping = m.YouGileMappingModel(
                id=uuid4(),
                team_id=self.team_id,
                entity_type=entity_type,
                yougile_id=external_id,
                last_synced_at=datetime.now(UTC),
            )
        mapping.local_id = local_id or mapping.local_id
        mapping.payload = payload if payload is not None else mapping.payload
        mapping.last_synced_at = datetime.now(UTC)
        self.session.add(mapping)

    async def _sync_event(
        self,
        direction: str,
        entity_type: str,
        entity_id: UUID | None,
        status: str,
        *,
        external_id: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            m.SyncEventModel(
                id=uuid4(),
                team_id=self.team_id,
                provider="yougile",
                direction=direction,
                action=entity_type,
                entity_type=entity_type,
                entity_id=entity_id,
                external_id=external_id,
                status=status,
                message=message,
                error=message if status == "error" else None,
                payload=payload,
            )
        )


async def grey_board_payload(session: AsyncSession, team_id: UUID, view: str = "agent") -> dict[str, Any]:
    team = await session.get(m.TeamModel, team_id)
    now = datetime.now(UTC)
    tasks = list(
        (
            await session.execute(
                select(m.TaskModel, m.UserModel, m.ExternalTaskLinkModel)
                .outerjoin(m.UserModel, m.UserModel.id == m.TaskModel.assignee_id)
                .outerjoin(
                    m.ExternalTaskLinkModel,
                    (m.ExternalTaskLinkModel.task_id == m.TaskModel.id)
                    & (m.ExternalTaskLinkModel.provider == "yougile"),
                )
                .where(m.TaskModel.team_id == team_id)
                .order_by(m.TaskModel.seq.desc())
            )
        ).all()
    )
    inbox_count = int(
        await session.scalar(
            select(func.count()).select_from(m.AiInboxItemModel).where(
                m.AiInboxItemModel.team_id == team_id,
                m.AiInboxItemModel.status == "pending",
            )
        )
        or 0
    )
    cards = [_card_payload(task, user, link, now) for task, user, link in tasks]
    recommendations = await recommendations_for_team(session, team_id)
    selected_board = await session.scalar(
        select(m.YouGileBoardModel).where(
            m.YouGileBoardModel.team_id == team_id,
            m.YouGileBoardModel.is_selected.is_(True),
        )
    )
    groups = _group_cards(cards, view, inbox_count)
    return {
        "team": {"id": str(team.id), "name": team.name, "timezone": team.timezone} if team else None,
        "view": view,
        "health": {
            "llm": "configured" if team and team.llm_settings_id else "needs_setup",
            "telegram": "linked" if team and team.tg_chat_id else "not_linked",
            "yougile": "synced" if selected_board else "not_selected",
            "open_risks": sum(1 for card in cards if card["signals"]),
            "last_sync": (
                selected_board.synced_at.isoformat()
                if selected_board and selected_board.synced_at
                else None
            ),
        },
        "groups": groups,
        "cards": cards,
        "recommendations": recommendations["items"],
    }


async def ai_inbox_payload(session: AsyncSession, team_id: UUID) -> dict[str, Any]:
    await ensure_generated_inbox(session, team_id)
    rows = (
        (
            await session.execute(
                select(m.AiInboxItemModel)
                .where(m.AiInboxItemModel.team_id == team_id)
                .order_by(m.AiInboxItemModel.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"items": [_inbox_payload(row) for row in rows]}


async def ensure_generated_inbox(session: AsyncSession, team_id: UUID) -> None:
    low_confidence = (
        (
            await session.execute(
                select(m.TaskProposalModel).where(
                    m.TaskProposalModel.team_id == team_id,
                    m.TaskProposalModel.confidence < 0.75,
                )
            )
        )
        .scalars()
        .all()
    )
    existing_sources = set(
        (
            await session.execute(
                select(m.AiInboxItemModel.source_id).where(m.AiInboxItemModel.team_id == team_id)
            )
        )
        .scalars()
        .all()
    )
    for proposal in low_confidence:
        source_id = str(proposal.id)
        if source_id in existing_sources:
            continue
        session.add(
            m.AiInboxItemModel(
                id=uuid4(),
                team_id=team_id,
                item_type="low_confidence_parse",
                kind="low_confidence",
                status="pending",
                source_type=proposal.source,
                source_id=source_id,
                source_text=proposal.raw_text,
                reason="low_confidence_parse",
                raw_text=proposal.raw_text,
                confidence=proposal.confidence,
                parsed_payload=proposal.extractor_payload,
                semantic_payload=proposal.extractor_payload,
                proposed_action="approve_task",
            )
        )
    await session.flush()


async def recommendations_for_team(session: AsyncSession, team_id: UUID) -> dict[str, Any]:
    now = datetime.now(UTC)
    rows = (
        (
            await session.execute(
                select(m.TaskModel, m.UserModel, m.ExternalTaskLinkModel)
                .outerjoin(m.UserModel, m.UserModel.id == m.TaskModel.assignee_id)
                .outerjoin(
                    m.ExternalTaskLinkModel,
                    (m.ExternalTaskLinkModel.task_id == m.TaskModel.id)
                    & (m.ExternalTaskLinkModel.provider == "yougile"),
                )
                .where(m.TaskModel.team_id == team_id)
            )
        )
        .all()
    )
    absent = set(
        (
            await session.execute(
                select(m.AbsencePeriodModel.user_id).where(
                    m.AbsencePeriodModel.team_id == team_id,
                    m.AbsencePeriodModel.status == "active",
                    m.AbsencePeriodModel.starts_at <= now,
                    (m.AbsencePeriodModel.ends_at.is_(None) | (m.AbsencePeriodModel.ends_at >= now)),
                )
            )
        )
        .scalars()
        .all()
    )
    items: list[dict[str, Any]] = []
    stale_by_user: dict[UUID, int] = {}
    for task, user, link in rows:
        if task.status in TERMINAL_STATUSES:
            continue
        if task.deadline and _as_utc(task.deadline) < now:
            items.append(_rec("overdue", "high", f"{task.public_id} просрочена", task, user, "open_task"))
        if (
            task.assignee_id
            and (
                task.last_status_update_at is None
                or _as_utc(task.last_status_update_at) < now - timedelta(days=2)
            )
        ):
            stale_by_user[task.assignee_id] = stale_by_user.get(task.assignee_id, 0) + 1
        if task.assignee_id in absent:
            items.append(_rec("absence_risk", "medium", f"{user.display_name if user else 'Сотрудник'} отсутствует, задача активна", task, user, "reassign"))
        if link and link.sync_status in {"error", "conflict"}:
            items.append(_rec("sync_issue", "high", f"YouGile sync: {link.sync_status}", task, user, "open_sync"))
    for user_id, count in stale_by_user.items():
        if count >= 2:
            user = await session.get(m.UserModel, user_id)
            items.append(
                {
                    "id": f"stale:{team_id}:{user_id}",
                    "kind": "missing_status",
                    "severity": "medium",
                    "title": f"Нет статуса по {count} задачам",
                    "message": f"У {user.display_name if user else 'сотрудника'} {count} задач без свежего отчета.",
                    "action": "ask_status",
                    "user_id": str(user_id),
                    "task_id": None,
                }
            )
    return {"items": items[:12]}


async def company_map_payload(session: AsyncSession, company_id: UUID) -> dict[str, Any]:
    company = await session.get(m.CompanyModel, company_id)
    teams = list(
        (
            await session.execute(
                select(m.TeamModel).where(m.TeamModel.company_id == company_id).order_by(m.TeamModel.name)
            )
        )
        .scalars()
        .all()
    )
    team_items = []
    for team in teams:
        board = await session.scalar(
            select(m.YouGileBoardModel).where(
                m.YouGileBoardModel.team_id == team.id,
                m.YouGileBoardModel.is_selected.is_(True),
            )
        )
        recs = await recommendations_for_team(session, team.id)
        open_tasks = int(
            await session.scalar(
                select(func.count()).select_from(m.TaskModel).where(
                    m.TaskModel.team_id == team.id,
                    m.TaskModel.status.notin_(list(TERMINAL_STATUSES)),
                )
            )
            or 0
        )
        overdue = int(
            await session.scalar(
                select(func.count()).select_from(m.TaskModel).where(
                    m.TaskModel.team_id == team.id,
                    m.TaskModel.deadline < datetime.now(UTC),
                    m.TaskModel.status.notin_(list(TERMINAL_STATUSES)),
                )
            )
            or 0
        )
        severity = "red" if overdue else "yellow" if recs["items"] else "green"
        team_items.append(
            {
                "id": str(team.id),
                "name": team.name,
                "manager": None,
                "open_tasks": open_tasks,
                "overdue": overdue,
                "risks": len(recs["items"]),
                "sync_health": "ok" if board else "not_configured",
                "status": severity,
            }
        )
    return {
        "company": {"id": str(company.id), "name": company.name, "timezone": company.timezone} if company else None,
        "teams": team_items,
    }


async def employee_profile_payload(
    session: AsyncSession,
    user_id: UUID,
    *,
    team_id: UUID | None = None,
) -> dict[str, Any]:
    user = await session.get(m.UserModel, user_id)
    statement = (
        select(m.TaskModel)
        .where(m.TaskModel.assignee_id == user_id)
        .order_by(m.TaskModel.deadline.is_(None), m.TaskModel.deadline, m.TaskModel.seq.desc())
    )
    if team_id:
        statement = statement.where(m.TaskModel.team_id == team_id)
    tasks = list((await session.execute(statement)).scalars().all())
    now = datetime.now(UTC)
    closed_week = [task for task in tasks if task.completed_at and _as_utc(task.completed_at) >= now - timedelta(days=7)]
    overdue = [task for task in tasks if task.deadline and _as_utc(task.deadline) < now and task.status not in TERMINAL_STATUSES]
    absence = await session.scalar(
        select(m.AbsencePeriodModel).where(
            m.AbsencePeriodModel.user_id == user_id,
            m.AbsencePeriodModel.status == "active",
            m.AbsencePeriodModel.starts_at <= now,
            (m.AbsencePeriodModel.ends_at.is_(None) | (m.AbsencePeriodModel.ends_at >= now)),
        )
    )
    xp = await session.scalar(select(m.UserXpTotalModel).where(m.UserXpTotalModel.user_id == user_id))
    from brain_api.application.use_cases.team_gamification import LEVEL_XP, level_for_points

    total_xp = xp.points_total if xp else 0
    level = xp.level if xp else level_for_points(total_xp)
    all_completed = [t for t in tasks if t.completed_at]
    total_closed = len(all_completed)
    streak = _completion_streak(all_completed, now)
    achievements = [
        {"name": "Первая кровь", "desc": "Закрыта первая задача", "icon": "🩸", "earned": total_closed >= 1},
        {"name": "Продуктивная неделя", "desc": "5 задач за неделю", "icon": "🔥", "earned": len(closed_week) >= 5},
        {"name": "Чистый дедлайн", "desc": "Нет просрочек", "icon": "✅", "earned": not overdue},
        {"name": "На связи", "desc": "Привязан Telegram", "icon": "📱", "earned": bool(user and user.telegram_user_id)},
        {"name": "Серия 3 дня", "desc": "3 дня подряд с закрытой задачей", "icon": "⚡", "earned": streak >= 3},
        {"name": "Ветеран", "desc": "Закрыто 25 задач", "icon": "🏆", "earned": total_closed >= 25},
        {"name": "5 уровень", "desc": "Достигнут 5 уровень", "icon": "🌟", "earned": level >= 5},
    ]
    return {
        "user": {
            "id": str(user.id),
            "display_name": user.display_name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "bio": user.bio,
            "photo_data_url": user.photo_data_url,
            "role": user.role,
            "telegram_linked": user.telegram_user_id is not None,
            "telegram_username": user.telegram_username,
        } if user else None,
        "stats": {
            "open_tasks": len([t for t in tasks if t.status not in TERMINAL_STATUSES]),
            "overdue": len(overdue),
            "closed_week": len(closed_week),
            "closed_total": total_closed,
            "streak": streak,
            "xp": total_xp,
            "level": level,
            "level_xp": total_xp % LEVEL_XP,
            "next_level_xp": LEVEL_XP,
        },
        "absence": {
            "active": absence is not None,
            "reason": absence.reason if absence else None,
            "delegate_to_user_id": str(absence.delegate_to_user_id) if absence and absence.delegate_to_user_id else None,
        },
        "digest": _personal_digest(tasks, overdue),
        "tasks": [_task_summary(task) for task in tasks],
        "achievements": achievements,
    }


def _completion_streak(completed_tasks: list, now: datetime) -> int:
    """Consecutive days (ending today or yesterday) with >=1 completed task."""
    days = {_as_utc(t.completed_at).date() for t in completed_tasks if t.completed_at}
    if not days:
        return 0
    today = now.date()
    if today not in days and (today - timedelta(days=1)) not in days:
        return 0
    streak = 0
    cursor = today if today in days else today - timedelta(days=1)
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _card_payload(
    task: m.TaskModel,
    user: m.UserModel | None,
    link: m.ExternalTaskLinkModel | None,
    now: datetime,
) -> dict[str, Any]:
    signals = []
    if task.deadline and _as_utc(task.deadline) < now and task.status not in TERMINAL_STATUSES:
        signals.append("просрочено")
    elif task.deadline and _as_utc(task.deadline) < now + timedelta(days=1) and task.status not in TERMINAL_STATUSES:
        signals.append("дедлайн скоро")
    if task.last_status_update_at is None or _as_utc(task.last_status_update_at) < now - timedelta(days=2):
        signals.append("нет статуса 2 дня")
    if link and link.sync_status == "conflict":
        signals.append("конфликт синхронизации")
    source_type = task.source_type or task.source or "manual"
    return {
        **_task_summary(task),
        "assignee_name": user.display_name if user else task.assignee_text,
        "source": {
            "type": source_type,
            "id": task.source_id,
            "text": task.source_text,
            "url": task.source_url,
        },
        "confidence": _confidence(task),
        "signals": signals,
        "agent_history": _agent_history(task, link),
        "yougile": {
            "external_task_id": link.external_task_id if link else None,
            "external_board_id": link.external_board_id if link else None,
            "external_column_id": link.external_column_id if link else None,
            "external_url": link.external_url if link else None,
            "last_sync": link.last_synced_at.isoformat() if link and link.last_synced_at else None,
            "sync_status": link.sync_status if link else "not_linked",
        },
    }


def _group_cards(cards: list[dict[str, Any]], view: str, inbox_count: int) -> list[dict[str, Any]]:
    if view == "status":
        columns = ["backlog", "todo", "in_progress", "blocked", "review", "done"]
        return [{"key": key, "title": _status_label(key), "cards": [c for c in cards if c["status"] == key]} for key in columns]
    if view == "people":
        names = sorted({card["assignee_name"] or "Без исполнителя" for card in cards})
        return [{"key": name, "title": name, "cards": [c for c in cards if (c["assignee_name"] or "Без исполнителя") == name]} for name in names]
    if view == "risk":
        buckets = {
            "overdue": "Просрочено",
            "soon": "Скоро дедлайн",
            "stale": "Нет статуса",
            "conflict": "Конфликты синхронизации",
        }
        return [
            {
                "key": key,
                "title": title,
                "cards": [card for card in cards if _risk_match(card, key)],
            }
            for key, title in buckets.items()
        ]
    if view == "timeline":
        return _timeline_groups(cards)
    if view == "source":
        sources = sorted({card["source"]["type"] or "manual" for card in cards})
        return [{"key": source, "title": _source_label(source), "cards": [c for c in cards if (c["source"]["type"] or "manual") == source]} for source in sources]
    return [
        {"key": "ai_inbox", "title": "AI Inbox", "cards": [], "count": inbox_count},
        {"key": "decision", "title": "Нужно решение", "cards": [c for c in cards if "конфликт синхронизации" in c["signals"]]},
        {"key": "active", "title": "Активные", "cards": [c for c in cards if c["status"] in {"todo", "in_progress", "review"} and not c["signals"]]},
        {"key": "waiting", "title": "Ждем статус", "cards": [c for c in cards if "нет статуса 2 дня" in c["signals"]]},
        {"key": "risks", "title": "Риски", "cards": [c for c in cards if c["signals"] and c["status"] not in TERMINAL_STATUSES]},
        {"key": "done", "title": "Готово", "cards": [c for c in cards if c["status"] in TERMINAL_STATUSES]},
    ]


def _timeline_groups(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    buckets: dict[str, list[dict[str, Any]]] = {
        "overdue": [],
        "today": [],
        "tomorrow": [],
        "week": [],
        "none": [],
    }
    for card in cards:
        raw = card.get("deadline")
        if not raw:
            buckets["none"].append(card)
            continue
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if value < now:
            buckets["overdue"].append(card)
        elif value.date() == now.date():
            buckets["today"].append(card)
        elif value.date() == (now + timedelta(days=1)).date():
            buckets["tomorrow"].append(card)
        elif value < now + timedelta(days=7):
            buckets["week"].append(card)
        else:
            buckets["none"].append(card)
    return [
        {"key": "overdue", "title": "Просрочено", "cards": buckets["overdue"]},
        {"key": "today", "title": "Сегодня", "cards": buckets["today"]},
        {"key": "tomorrow", "title": "Завтра", "cards": buckets["tomorrow"]},
        {"key": "week", "title": "На неделе", "cards": buckets["week"]},
        {"key": "none", "title": "Без дедлайна", "cards": buckets["none"]},
    ]


def _rec(
    kind: str,
    severity: str,
    message: str,
    task: m.TaskModel,
    user: m.UserModel | None,
    action: str,
) -> dict[str, Any]:
    return {
        "id": f"{kind}:{task.id}",
        "kind": kind,
        "severity": severity,
        "title": message,
        "message": f"{task.public_id} · {task.title}",
        "action": action,
        "task_id": str(task.id),
        "user_id": str(user.id) if user else None,
    }


def _risk_match(card: dict[str, Any], key: str) -> bool:
    signals = set(card["signals"])
    return {
        "overdue": "просрочено" in signals,
        "soon": "дедлайн скоро" in signals,
        "stale": "нет статуса 2 дня" in signals,
        "conflict": "конфликт синхронизации" in signals,
    }.get(key, False)


def _inbox_payload(row: m.AiInboxItemModel) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "type": row.item_type,
        "status": row.status,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "source_text": row.source_text,
        "confidence": row.confidence,
        "parsed_payload": row.parsed_payload or {},
        "proposed_action": row.proposed_action,
        "linked_task_id": str(row.linked_task_id) if row.linked_task_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _task_summary(task: m.TaskModel) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "public_id": task.public_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "assignee_id": str(task.assignee_id) if task.assignee_id else None,
        "assignee_text": task.assignee_text,
        "deadline": _as_utc(task.deadline).isoformat() if task.deadline else None,
        "deadline_timezone": task.deadline_timezone,
        "source_type": task.source_type or task.source,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _personal_digest(tasks: list[m.TaskModel], overdue: list[m.TaskModel]) -> str:
    active = [task for task in tasks if task.status not in TERMINAL_STATUSES]
    if overdue:
        return f"Есть {len(overdue)} просроченных задач. Начни с {overdue[0].public_id}."
    if active:
        return f"В работе {len(active)} задач. Ближайшая: {active[0].public_id}."
    return "Активных задач нет."


def _apply_yougile_payload(task: m.TaskModel, payload: dict[str, Any], status_name: str) -> None:
    task.title = str(payload.get("title") or task.title)
    if "description" in payload:
        task.description = payload.get("description")
    task.status = "done" if payload.get("completed") else status_name
    task.deadline = _deadline_from_yougile(payload.get("deadline"))
    task.priority = _priority_from_payload(payload)
    task.source_type = task.source_type or "yougile_board"
    task.source_payload = payload
    task.last_status_update_at = datetime.now(UTC)
    if task.status == "done":
        task.completed_at = datetime.now(UTC)


def _task_differs(task: m.TaskModel, payload: dict[str, Any], status_name: str) -> bool:
    return (payload.get("title") and str(payload["title"]) != task.title) or status_name != task.status


def _deadline_from_yougile(value: Any) -> datetime | None:
    if isinstance(value, dict) and value.get("deadline"):
        return datetime.fromtimestamp(float(value["deadline"]) / 1000, tz=UTC)
    return None


def _deadline_to_yougile(value: datetime | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"deadline": int(_as_utc(value).timestamp() * 1000), "withTime": True}


def _priority_from_payload(payload: dict[str, Any]) -> str:
    raw = str(payload.get("priority") or payload.get("importance") or "").lower()
    if raw in {"high", "urgent", "critical", "высокий"}:
        return "high"
    if raw in {"low", "низкий"}:
        return "low"
    return "medium"


def _confidence(task: m.TaskModel) -> float:
    payload = task.source_payload if isinstance(task.source_payload, dict) else {}
    return float(payload.get("confidence") or payload.get("gc_confidence") or 0.87)


def _agent_history(task: m.TaskModel, link: m.ExternalTaskLinkModel | None) -> list[dict[str, str]]:
    items = [
        {"at": task.created_at.isoformat() if task.created_at else "", "text": "агент нашел или импортировал задачу"},
    ]
    if task.created_from_proposal_id:
        items.append({"at": task.created_at.isoformat(), "text": "предложение подтверждено человеком"})
    if link:
        items.append({"at": link.last_synced_at.isoformat() if link.last_synced_at else "", "text": f"YouGile sync: {link.sync_status}"})
    if task.last_status_update_at:
        items.append({"at": task.last_status_update_at.isoformat(), "text": "обновлен статус"})
    return items


def _column_for_status(columns: list[m.YouGileColumnModel], status: str) -> m.YouGileColumnModel | None:
    return next((column for column in columns if column.mapped_status == status), None)


def _project_id(project: m.YouGileProjectModel | None) -> UUID | None:
    return project.id if project is not None else None


def _name(payload: dict[str, Any]) -> str:
    return str(payload.get("title") or payload.get("name") or payload.get("realName") or payload.get("id") or "")


def _status_label(status_name: str) -> str:
    return {
        "backlog": "Backlog",
        "todo": "Todo",
        "in_progress": "In Progress",
        "blocked": "Blocked",
        "review": "Review",
        "done": "Done",
    }.get(status_name, status_name)


def _source_label(source: str) -> str:
    return {
        "telegram": "Telegram chat",
        "telegram_topic": "Telegram topic",
        "yougile": "YouGile import",
        "yougile_board": "YouGile board",
        "meeting": "Meeting transcript",
        "daily_sync": "Daily sync",
        "manual": "Manual",
    }.get(source, source)


def _board_payload(board: m.YouGileBoardModel) -> dict[str, Any]:
    return {
        "id": str(board.id),
        "external_id": board.external_id,
        "name": board.name,
        "is_selected": board.is_selected,
        "synced_at": board.synced_at.isoformat() if board.synced_at else None,
    }


def _yougile_task_url(payload: dict[str, Any]) -> str | None:
    return payload.get("url") or payload.get("link") or payload.get("htmlUrl")


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _maybe_call(client: Any, method: str, default: Any) -> Any:
    func_obj = getattr(client, method, None)
    if func_obj is None:
        return default
    try:
        return await func_obj()
    except Exception:  # noqa: BLE001
        return default
