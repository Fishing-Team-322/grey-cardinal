"""Discover a team's YouGile workspace and mirror it into yougile_mappings.

Idempotent (UNIQUE(team_id, entity_type, yougile_id)) so it can run on connect,
on manual refresh, and on a 6h schedule. Bootstraps an empty YouGile account with
a default project/board/columns. Never raises into the caller's request path —
errors are logged to yougile_sync_log.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from brain_api.infrastructure.db import models as m
from brain_api.integrations.yougile import (
    YouGileAuthError,
    YouGileClient,
    YouGileError,
    YouGileMappingRepo,
)

logger = logging.getLogger(__name__)

_DEFAULT_COLUMNS = (
    ("todo", "К выполнению", 7),
    ("in_progress", "В работе", 3),
    ("done", "Готово", 5),
)


def make_client(api_key: str, base_url: str) -> YouGileClient:
    return YouGileClient(api_key, base_url=base_url)


async def discover_yougile_workspace(
    session_factory: async_sessionmaker,
    *,
    team_id: UUID,
    api_base_url: str,
    cipher,
    client: YouGileClient | None = None,
) -> dict[str, Any]:
    """Pull projects/boards/columns/tasks/users into mappings. Returns stats."""
    async with session_factory() as session:
        team = await session.get(m.TeamModel, team_id)
        if team is None or not team.board_credentials_encrypted:
            return {"ok": False, "reason": "team not connected"}
        api_key = _api_key(team, cipher)
        yc = client or make_client(api_key, api_base_url)
        repo = YouGileMappingRepo(session, team_id)
        config = dict(team.board_config or {})

        try:
            projects = await yc.list_projects()
        except YouGileAuthError as exc:
            repo.log(direction="inbound", event="discover", error=f"auth: {exc.status}")
            await session.commit()
            return {"ok": False, "reason": "auth_error"}
        except YouGileError as exc:
            repo.log(direction="inbound", event="discover", error=str(exc))
            await session.commit()
            return {"ok": False, "reason": "error"}

        if not projects:
            primary = await _bootstrap_empty(yc, repo, team, config)
            projects = [primary] if primary else []
        for p in projects:
            await repo.upsert("project", str(p["id"]), payload=p)

        primary_id = _pick_primary(projects, config)
        stats = {"projects": len(projects), "boards": 0, "columns": 0, "tasks": 0, "users": 0}

        if primary_id:
            config["yougile_project_id"] = primary_id
            config["yougile_project_name"] = _title_of(projects, primary_id)
            boards = await yc.list_boards(project_id=primary_id)
            for b in boards:
                await repo.upsert("board", str(b["id"]), payload=b)
                stats["boards"] += 1
                columns = await yc.list_columns(board_id=str(b["id"]))
                for col in columns:
                    await repo.upsert("column", str(col["id"]), payload=col)
                    stats["columns"] += 1
                    tasks = await yc.list_tasks(column_id=str(col["id"]))
                    for t in tasks:
                        await repo.upsert("task", str(t["id"]), payload=t)
                        stats["tasks"] += 1
            if boards and not config.get("default_board_id"):
                config["default_board_id"] = str(boards[0]["id"])
            _ensure_default_columns(
                config,
                await yc.list_columns(board_id=config.get("default_board_id"))
                if config.get("default_board_id")
                else [],
            )

        users = await yc.list_users()
        await _map_users(session, repo, team_id, users)
        stats["users"] = len(users)

        config["synced_at"] = datetime.now(UTC).isoformat()
        team.board_config = config
        repo.log(direction="inbound", event="discover", payload=stats)
        await session.commit()
        return {"ok": True, "stats": stats, "primary_project_id": primary_id}


def _api_key(team: m.TeamModel, cipher) -> str:
    import json

    raw = cipher.decrypt_text(team.board_credentials_encrypted) or "{}"
    return json.loads(raw).get("api_key", "")


def _pick_primary(projects: list[dict], config: dict) -> str | None:
    if config.get("yougile_project_id"):
        return config["yougile_project_id"]
    if len(projects) == 1:
        return str(projects[0]["id"])
    return None  # >1 project: UI picks


def _title_of(projects: list[dict], pid: str) -> str | None:
    for p in projects:
        if str(p["id"]) == pid:
            return p.get("title")
    return None


def _ensure_default_columns(config: dict, columns: list[dict]) -> None:
    """Best-effort: map our statuses onto the board's columns by title."""
    if config.get("default_column_ids"):
        return
    by_title = {(c.get("title") or "").strip().lower(): str(c["id"]) for c in columns}
    mapping = {}
    for status_key, title, _ in _DEFAULT_COLUMNS:
        cid = by_title.get(title.lower())
        if cid:
            mapping[status_key] = cid
    # Fallback: first three columns in order.
    if len(mapping) < 3 and len(columns) >= 3:
        for (status_key, _, _), col in zip(_DEFAULT_COLUMNS, columns, strict=False):
            mapping.setdefault(status_key, str(col["id"]))
    if mapping:
        config["default_column_ids"] = mapping


async def _bootstrap_empty(yc: YouGileClient, repo: YouGileMappingRepo, team, config: dict):
    """Create project + board + 3 columns for an empty YouGile account."""
    project = await yc.create_project(title=team.name)
    pid = str(project["id"])
    project = {"id": pid, "title": team.name}
    board = await yc.create_board(title="Основная", project_id=pid)
    bid = str(board["id"])
    await repo.upsert("board", bid, payload={"id": bid, "title": "Основная", "projectId": pid})
    default_cols: dict[str, str] = {}
    for status_key, title, color in _DEFAULT_COLUMNS:
        col = await yc.create_column(title=title, board_id=bid, color=color)
        cid = str(col["id"])
        await repo.upsert("column", cid, payload={"id": cid, "title": title, "boardId": bid})
        default_cols[status_key] = cid
    config["default_board_id"] = bid
    config["default_column_ids"] = default_cols
    repo.log(direction="outbound", event="bootstrap", yougile_id=pid, payload={"board": bid})
    return project


async def _map_users(session, repo: YouGileMappingRepo, team_id: UUID, users: list[dict]) -> None:
    """Match YouGile users to team members by email (best-effort)."""
    from sqlalchemy import select

    rows = await session.execute(
        select(m.UserModel.id, m.UserModel.email)
        .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
        .where(m.TeamMemberModel.team_id == team_id)
    )
    email_to_local = {(e or "").lower(): uid for uid, e in rows.all()}
    for u in users:
        local_id = email_to_local.get((u.get("email") or "").lower())
        await repo.upsert("user", str(u["id"]), local_id=local_id, payload=u)
