from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskPriority, TaskSource, TaskStatus
from brain_api.infrastructure.board.yougile import YouGileBoardAdapter
from brain_api.infrastructure.db import models as m
from brain_api.integrations.yougile import YouGileAuthError, YouGileMappingRepo


class FakeClient:
    def __init__(self, *, auth_error: bool = False) -> None:
        self.auth_error = auth_error
        self.created: list[dict] = []
        self.updated: list[tuple[str, dict]] = []
        self.comments: list[tuple[str, str]] = []

    async def create_task(self, title, column_id, **fields):
        if self.auth_error:
            raise YouGileAuthError("POST", "/tasks", 401, "invalid key")
        payload = {"id": "yg-task-1", "title": title, "columnId": column_id, **fields}
        self.created.append(payload)
        return {"id": "yg-task-1"}

    async def update_task(self, task_id, **fields):
        self.updated.append((task_id, fields))
        return {"id": task_id}

    async def create_chat_message(self, task_id, text):
        self.comments.append((task_id, text))
        return {"id": "message-1"}


async def _seed_team(session_factory):
    async with session_factory() as session:
        user = m.UserModel(id=uuid4(), display_name="User", email="user@example.com", login="user")
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
        )
        session.add_all([user, company, team])
        await session.commit()
        return user.id, team.id


def _task(team_id, assignee_id=None):
    return Task(
        id=uuid4(),
        public_id="GC-1",
        title="Ship integration",
        status=TaskStatus.todo,
        priority=TaskPriority.high,
        source=TaskSource.manual,
        team_id=team_id,
        assignee_id=assignee_id,
        deadline=datetime(2026, 6, 12, 15, 30, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_create_card_maps_assignee_deadline_and_task(session_factory):
    user_id, team_id = await _seed_team(session_factory)
    async with session_factory() as session:
        repo = YouGileMappingRepo(session, team_id)
        await repo.upsert("user", "yg-user-1", local_id=user_id)
        await session.commit()

    client = FakeClient()
    task = _task(team_id, user_id)
    adapter = YouGileBoardAdapter(
        session_factory,
        team_id,
        client,
        {"todo": "col-todo", "in_progress": "col-progress", "done": "col-done"},
    )

    result = await adapter.create_card(task)

    assert result.external_card_id == "yg-task-1"
    assert client.created[0]["assigned"] == ["yg-user-1"]
    assert client.created[0]["deadline"] == {
        "deadline": int(task.deadline.timestamp() * 1000),
        "withTime": True,
    }
    async with session_factory() as session:
        mapping = await YouGileMappingRepo(session, team_id).find_by_local("task", task.id)
        assert mapping is not None
        assert mapping.yougile_id == "yg-task-1"


@pytest.mark.asyncio
async def test_move_close_and_comment_use_verified_endpoints(session_factory):
    _, team_id = await _seed_team(session_factory)
    client = FakeClient()
    adapter = YouGileBoardAdapter(
        session_factory,
        team_id,
        client,
        {"todo": "col-todo", "in_progress": "col-progress", "done": "col-done"},
    )

    await adapter.move_card("yg-task-1", TaskStatus.in_progress)
    await adapter.close_card("yg-task-1")
    await adapter.add_comment("yg-task-1", "Ready <today>")

    assert client.updated == [
        ("yg-task-1", {"columnId": "col-progress"}),
        ("yg-task-1", {"completed": True, "columnId": "col-done"}),
    ]
    assert client.comments == [("yg-task-1", "Ready <today>")]


@pytest.mark.asyncio
async def test_auth_error_falls_back_to_mock_without_losing_local_task(session_factory):
    _, team_id = await _seed_team(session_factory)
    task = _task(team_id)
    adapter = YouGileBoardAdapter(
        session_factory,
        team_id,
        FakeClient(auth_error=True),
        {"todo": "col-todo"},
    )

    result = await adapter.create_card(task)

    assert result.external_card_id == ""
    async with session_factory() as session:
        team = await session.get(m.TeamModel, team_id)
        assert team.board_provider == "mock"
        assert team.board_config["integration_status"] == "auth_error"
        errors = (
            (
                await session.execute(
                    select(m.YouGileSyncLogModel).where(m.YouGileSyncLogModel.team_id == team_id)
                )
            )
            .scalars()
            .all()
        )
        assert errors[-1].error == "auth:401"
