from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from brain_api.api.deps import get_container
from brain_api.api.routes import yougile_webhooks as routes
from brain_api.api.routes.accounts import get_db
from brain_api.infrastructure.board.yougile import mark_outbound
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.events.event_bus import NullEventPublisher


@pytest_asyncio.fixture
async def connected_team(session_factory):
    async with session_factory() as session:
        user = m.UserModel(id=uuid4(), display_name="User", email="u@example.com", login="u")
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
            board_config={
                "webhook_secret": "hook-secret",
                "default_column_ids": {
                    "todo": "col-todo",
                    "in_progress": "col-progress",
                    "done": "col-done",
                },
            },
        )
        session.add_all([user, company, team])
        await session.commit()
        return team.id


@pytest.fixture
def webhook_client(session_factory):
    events = NullEventPublisher()
    app = FastAPI()
    app.include_router(routes.router)

    async def _db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(event_publisher=events)
    return TestClient(app), events


def _url(team_id, event, secret="hook-secret"):
    return f"/api/integrations/yougile/webhook/{team_id}?event={event}&secret={secret}"


def test_webhook_rejects_invalid_secret(webhook_client, connected_team):
    client, _ = webhook_client
    response = client.post(
        _url(connected_team, "task-created", secret="wrong"),
        json={"id": "remote-1", "title": "Remote"},
    )
    assert response.status_code == 401


def test_task_created_and_moved_are_mirrored(
    webhook_client,
    connected_team,
    session_factory,
):
    client, events = webhook_client

    async def _seed_assignee():
        async with session_factory() as session:
            user = await session.scalar(select(m.UserModel))
            session.add_all(
                [
                    m.TeamMemberModel(
                        team_id=connected_team,
                        user_id=user.id,
                        role="employee",
                    ),
                    m.YouGileMappingModel(
                        team_id=connected_team,
                        entity_type="user",
                        local_id=user.id,
                        yougile_id="remote-user",
                        last_synced_at=datetime.now(UTC),
                    ),
                ]
            )
            await session.commit()

    import asyncio

    asyncio.run(_seed_assignee())
    created = client.post(
        _url(connected_team, "task-created"),
        json={
            "id": "remote-1",
            "title": "Remote task",
            "columnId": "col-todo",
            "assigned": ["remote-user"],
            "deadline": {"deadline": 1781278200000, "withTime": True},
        },
    )
    assert created.status_code == 202, created.text

    moved = client.post(
        _url(connected_team, "task-moved"),
        json={
            "id": "remote-1",
            "title": "Remote task",
            "columnId": "col-done",
            "completed": True,
            "assigned": ["remote-user"],
        },
    )
    assert moved.status_code == 202, moved.text
    assert [event.event.value for event in events.events] == [
        "task_created",
        "task_status_changed",
    ]

    async def _assert_db():
        async with session_factory() as session:
            mapping = await session.scalar(
                select(m.YouGileMappingModel).where(
                    m.YouGileMappingModel.team_id == connected_team,
                    m.YouGileMappingModel.yougile_id == "remote-1",
                )
            )
            task = await session.get(m.TaskModel, mapping.local_id)
            assert task.status == "done"
            assert task.source == "yougile_import"
            assert task.completed_at is not None
            link = await session.scalar(
                select(m.ExternalTaskLinkModel).where(
                    m.ExternalTaskLinkModel.team_id == connected_team,
                    m.ExternalTaskLinkModel.external_task_id == "remote-1",
                )
            )
            assert link is not None
            assert link.task_id == task.id
            assert link.external_column_id == "col-done"
            xp = await session.scalar(
                select(m.UserXpEventModel).where(
                    m.UserXpEventModel.user_id == task.assignee_id,
                    m.UserXpEventModel.kind == "task_completed",
                )
            )
            assert xp is not None

    asyncio.run(_assert_db())


def test_existing_external_link_prevents_delayed_webhook_duplicate(
    webhook_client,
    connected_team,
    session_factory,
):
    client, _ = webhook_client

    async def _seed_link():
        async with session_factory() as session:
            task = m.TaskModel(
                id=uuid4(),
                seq=1,
                public_id="GC-1",
                team_id=connected_team,
                title="Original",
                status="todo",
                priority="medium",
                source="manual",
            )
            session.add(task)
            await session.flush()
            session.add(
                m.ExternalTaskLinkModel(
                    team_id=connected_team,
                    task_id=task.id,
                    provider="yougile",
                    external_board_id="board-1",
                    external_column_id="col-todo",
                    external_task_id="remote-existing",
                    sync_status="synced",
                )
            )
            await session.commit()
            return task.id

    import asyncio

    task_id = asyncio.run(_seed_link())
    response = client.post(
        _url(connected_team, "task-updated"),
        json={
            "id": "remote-existing",
            "title": "Updated once",
            "columnId": "col-progress",
        },
    )
    assert response.status_code == 202, response.text
    assert response.json()["task_id"] == str(task_id)

    async def _assert_db():
        async with session_factory() as session:
            tasks = list(
                await session.scalars(
                    select(m.TaskModel).where(m.TaskModel.team_id == connected_team)
                )
            )
            assert len(tasks) == 1
            assert tasks[0].title == "Updated once"
            assert tasks[0].status == "in_progress"

    asyncio.run(_assert_db())


def test_recent_outbound_echo_is_ignored(webhook_client, connected_team):
    client, events = webhook_client
    mark_outbound(connected_team, "remote-echo")

    response = client.post(
        _url(connected_team, "task-updated"),
        json={"id": "remote-echo", "title": "Echo"},
    )

    assert response.status_code == 202
    assert response.json()["ignored"] == "outbound_echo"
    assert events.events == []


def test_webhook_rate_limit_is_per_team(monkeypatch):
    team_id = uuid4()
    routes._received_at[team_id] = deque([0.0] * 100)
    monkeypatch.setattr(routes.time, "monotonic", lambda: 30.0)

    with pytest.raises(HTTPException) as exc:
        routes._check_rate_limit(team_id)

    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "30"
