import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from yougile_fakes import FakeYouGile

from brain_api.application.board_mirror import BoardMirrorService
from brain_api.config import Settings
from brain_api.domain.enums import TaskStatus
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher


@pytest.mark.asyncio
async def test_board_mirror_creates_link_and_moves_task(session_factory):
    key = "test-board-key"
    settings = Settings(
        llm_provider="disabled",
        board_creds_encryption_key=key,
        yougile_api_base_url="https://example.invalid",
    )
    fake = FakeYouGile()
    async with session_factory() as session:
        owner = m.UserModel(id=uuid4(), display_name="Owner")
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=owner.id
        )
        team = m.TeamModel(
            id=uuid4(),
            company_id=company.id,
            name="Team",
            timezone="Europe/Moscow",
            board_provider="yougile",
            board_credentials_encrypted=SecretCipher(key).encrypt_text(
                json.dumps({"api_key": "fake"})
            ),
        )
        board = m.YouGileBoardModel(
            id=uuid4(),
            team_id=team.id,
            external_id="board-1",
            name="Board",
            is_selected=True,
        )
        todo = m.YouGileColumnModel(
            id=uuid4(),
            board_id=board.id,
            external_id="todo-1",
            name="Todo",
            mapped_status="todo",
        )
        done = m.YouGileColumnModel(
            id=uuid4(),
            board_id=board.id,
            external_id="done-1",
            name="Done",
            mapped_status="done",
            position=1,
        )
        task = m.TaskModel(
            id=uuid4(),
            seq=1,
            public_id="GC-1",
            team_id=team.id,
            title="Подготовить отчёт",
            status="todo",
            priority="medium",
            source="manual",
        )
        session.add_all([owner, company, team, board, todo, done, task])
        await session.commit()
        task_id = task.id

    mirror = BoardMirrorService(session_factory, settings, client_factory=lambda _: fake)
    created = await mirror.create_external_task(task_id)
    moved = await mirror.close_task(task_id)

    assert created.ok is True
    assert moved.ok is True
    async with session_factory() as session:
        link = await session.scalar(
            select(m.ExternalTaskLinkModel).where(
                m.ExternalTaskLinkModel.task_id == task_id
            )
        )
        task = await session.get(m.TaskModel, task_id)
        assert link is not None
        assert link.sync_status == "synced"
        assert link.external_column_id == "done-1"
        assert task.status == TaskStatus.done.value


@pytest.mark.asyncio
async def test_board_mirror_updates_existing_task_without_duplicate(session_factory):
    key = "test-board-key"
    settings = Settings(
        llm_provider="disabled",
        board_creds_encryption_key=key,
        yougile_api_base_url="https://example.invalid",
    )
    fake = FakeYouGile()
    async with session_factory() as session:
        owner = m.UserModel(id=uuid4(), display_name="Owner")
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=owner.id
        )
        team = m.TeamModel(
            id=uuid4(),
            company_id=company.id,
            name="Team",
            timezone="Europe/Moscow",
            board_provider="yougile",
            board_credentials_encrypted=SecretCipher(key).encrypt_text(
                json.dumps({"api_key": "fake"})
            ),
        )
        board = m.YouGileBoardModel(
            id=uuid4(), team_id=team.id, external_id="board-1", name="Board", is_selected=True
        )
        todo = m.YouGileColumnModel(
            id=uuid4(),
            board_id=board.id,
            external_id="todo-1",
            name="Todo",
            mapped_status="todo",
        )
        task = m.TaskModel(
            id=uuid4(),
            seq=2,
            public_id="GC-2",
            team_id=team.id,
            title="Новая формулировка",
            status="todo",
            priority="medium",
            source="manual",
        )
        link = m.ExternalTaskLinkModel(
            id=uuid4(),
            team_id=team.id,
            task_id=task.id,
            provider="yougile",
            external_board_id=board.external_id,
            external_column_id=todo.external_id,
            external_task_id="existing-task",
            sync_status="pending_update",
        )
        session.add_all([owner, company, team, board, todo, task, link])
        await session.commit()
        team_id = team.id

    mirror = BoardMirrorService(session_factory, settings, client_factory=lambda _: fake)
    result = await mirror.sync_outbound(team_id)

    assert result["synced"] == 1
    assert fake.created["task"] == []
    assert fake.created["task_update"][0]["id"] == "existing-task"
    assert fake.created["task_update"][0]["title"] == "GC-2 Новая формулировка"


@pytest.mark.asyncio
async def test_import_does_not_mutate_link_owned_by_another_team(session_factory):
    key = "test-board-key"
    settings = Settings(
        llm_provider="disabled",
        board_creds_encryption_key=key,
        yougile_api_base_url="https://example.invalid",
    )
    fake = FakeYouGile(tasks={"todo-2": [{"id": "shared-task", "title": "Foreign"}]})
    async with session_factory() as session:
        owner = m.UserModel(id=uuid4(), display_name="Owner")
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=owner.id
        )
        first_team = m.TeamModel(
            id=uuid4(), company_id=company.id, name="First", timezone="Europe/Moscow"
        )
        second_team = m.TeamModel(
            id=uuid4(),
            company_id=company.id,
            name="Second",
            timezone="Europe/Moscow",
            board_provider="yougile",
            board_credentials_encrypted=SecretCipher(key).encrypt_text(
                json.dumps({"api_key": "fake"})
            ),
        )
        board = m.YouGileBoardModel(
            id=uuid4(),
            team_id=second_team.id,
            external_id="board-2",
            name="Board",
            is_selected=True,
        )
        column = m.YouGileColumnModel(
            id=uuid4(),
            board_id=board.id,
            external_id="todo-2",
            name="Todo",
            mapped_status="todo",
        )
        foreign_task = m.TaskModel(
            id=uuid4(),
            seq=3,
            public_id="GC-3",
            team_id=first_team.id,
            title="Original",
            status="todo",
            priority="medium",
            source="manual",
        )
        link = m.ExternalTaskLinkModel(
            id=uuid4(),
            team_id=first_team.id,
            task_id=foreign_task.id,
            provider="yougile",
            external_board_id="other-board",
            external_task_id="shared-task",
            sync_status="synced",
        )
        session.add_all(
            [owner, company, first_team, second_team, board, column, foreign_task, link]
        )
        await session.commit()
        second_team_id = second_team.id
        foreign_task_id = foreign_task.id

    mirror = BoardMirrorService(session_factory, settings, client_factory=lambda _: fake)
    summary = await mirror.import_selected_board(second_team_id)

    assert summary.skipped_tasks == 1
    async with session_factory() as session:
        foreign_task = await session.get(m.TaskModel, foreign_task_id)
        assert foreign_task is not None
        assert foreign_task.title == "Original"
