from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.deps import get_container
from brain_api.api.routes import yougile_board as routes
from brain_api.api.routes.accounts import get_current_user, get_db
from brain_api.infrastructure.db import models as m


class RecordingWebsocketManager:
    def __init__(self) -> None:
        self.messages = []

    async def broadcast(self, message):
        self.messages.append(message)


@pytest_asyncio.fixture
async def board_data(session_factory):
    async with session_factory() as session:
        user = m.UserModel(id=uuid4(), display_name="Manager", email="m@example.com", login="m")
        company = m.CompanyModel(
            id=uuid4(),
            name="Company",
            timezone="Europe/Moscow",
            created_by=user.id,
        )
        team = m.TeamModel(
            id=uuid4(),
            company_id=company.id,
            name="Team",
            timezone="Europe/Moscow",
            board_provider="yougile",
            board_credentials_encrypted=b"encrypted",
            board_config={"yougile_project_id": "project-1"},
        )
        session.add_all([user, company, team])
        session.add(m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=user.id, role="manager"))
        rows = [
            m.YouGileMappingModel(
                team_id=team.id,
                entity_type="project",
                yougile_id="project-1",
                payload={"id": "project-1", "title": "Project"},
            ),
            m.YouGileMappingModel(
                team_id=team.id,
                entity_type="board",
                yougile_id="board-1",
                payload={"id": "board-1", "title": "Board", "projectId": "project-1"},
            ),
            m.YouGileMappingModel(
                team_id=team.id,
                entity_type="column",
                yougile_id="column-1",
                payload={"id": "column-1", "title": "Todo", "boardId": "board-1"},
            ),
            m.YouGileMappingModel(
                team_id=team.id,
                entity_type="user",
                yougile_id="yg-user-1",
                local_id=user.id,
                payload={"id": "yg-user-1", "realName": "Manager"},
            ),
            m.YouGileMappingModel(
                team_id=team.id,
                entity_type="task",
                yougile_id="task-1",
                payload={
                    "id": "task-1",
                    "title": "Task",
                    "columnId": "column-1",
                    "assigned": ["yg-user-1"],
                    "deadline": {"deadline": 1781278200000},
                    "stickers": {"sticker-1": "state-1"},
                },
            ),
        ]
        for row in rows:
            row.last_synced_at = datetime.now(UTC)
        session.add_all(rows)
        await session.commit()
        return user.id, team.id


@pytest.fixture
def client(session_factory, board_data, monkeypatch):
    user_id, _ = board_data
    websocket_manager = RecordingWebsocketManager()
    container = SimpleNamespace(
        session_factory=session_factory,
        websocket_manager=websocket_manager,
    )

    async def _discover(*args, **kwargs):
        return {"ok": True, "stats": {"projects": 1}}

    monkeypatch.setattr(routes, "discover_yougile_workspace", _discover)
    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(routes.sync_router)

    async def _db():
        async with session_factory() as session:
            yield session

    async def _user():
        async with session_factory() as session:
            return await session.get(m.UserModel, user_id)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_container] = lambda: container
    return TestClient(app), websocket_manager


def test_board_read_endpoints(client, board_data):
    http, _ = client
    _, team_id = board_data

    projects = http.get(f"/api/teams/{team_id}/board/projects")
    assert projects.status_code == 200
    assert projects.json() == [
        {
            "id": "project-1",
            "name": "Project",
            "is_primary": True,
            "boards_count": 1,
        }
    ]

    boards = http.get(f"/api/teams/{team_id}/board/projects/project-1/boards")
    assert boards.status_code == 200
    assert boards.json()[0]["columns"] == [{"id": "column-1", "name": "Todo", "tasks_count": 1}]

    tasks = http.get(f"/api/teams/{team_id}/board/columns/column-1/tasks")
    assert tasks.status_code == 200
    assert tasks.json()[0]["assigned"][0]["name"] == "Manager"
    assert tasks.json()[0]["stickers"] == [{"id": "sticker-1", "value": "state-1"}]


def test_manual_sync_returns_job_and_publishes_progress(client, board_data):
    http, websocket_manager = client
    _, team_id = board_data

    response = http.post(f"/api/teams/{team_id}/integrations/yougile/sync")

    assert response.status_code == 202
    assert response.json()["job_id"]
    assert [message["payload"]["state"] for message in websocket_manager.messages] == [
        "started",
        "completed",
    ]
