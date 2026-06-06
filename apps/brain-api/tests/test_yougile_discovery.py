"""discover_yougile_workspace: mirror populated account + bootstrap empty one."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from brain_api.application.use_cases.yougile_discovery import discover_yougile_workspace
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher
from brain_api.integrations.yougile import YouGileMappingRepo
from yougile_fakes import FakeYouGile

CIPHER = SecretCipher("unit-test-encryption-key")


async def _seed_connected_team(session, member_email="member@example.com"):
    user = m.UserModel(id=uuid4(), display_name="M", email=member_email, login="m")
    company = m.CompanyModel(id=uuid4(), name="C", timezone="Europe/Moscow", created_by=user.id)
    team = m.TeamModel(
        id=uuid4(), company_id=company.id, name="Команда А", timezone="Europe/Moscow",
        board_provider="yougile",
        board_credentials_encrypted=CIPHER.encrypt_text(json.dumps({"api_key": "k"})),
    )
    session.add_all([user, company, team])
    session.add(m.TeamMemberModel(id=uuid4(), team_id=team.id, user_id=user.id, role="manager"))
    await session.commit()
    return team


@pytest.mark.asyncio
async def test_discovery_mirrors_populated_account(session_factory):
    async with session_factory() as session:
        team = await _seed_connected_team(session)
    fake = FakeYouGile(
        projects=[{"id": "p1", "title": "Proj"}],
        boards=[{"id": "b1", "title": "Board", "projectId": "p1"}],
        columns=[
            {"id": "c-todo", "title": "К выполнению", "boardId": "b1"},
            {"id": "c-prog", "title": "В работе", "boardId": "b1"},
            {"id": "c-done", "title": "Готово", "boardId": "b1"},
        ],
        tasks={"c-todo": [{"id": "t1", "title": "Task"}]},
        users=[{"id": "u1", "email": "member@example.com"}],
    )
    res = await discover_yougile_workspace(
        session_factory, team_id=team.id, api_base_url="x", cipher=CIPHER, client=fake
    )
    assert res["ok"] is True
    assert res["stats"] == {"projects": 1, "boards": 1, "columns": 3, "tasks": 1, "users": 1}

    async with session_factory() as session:
        repo = YouGileMappingRepo(session, team.id)
        assert await repo.count_by_type("task") == 1
        assert await repo.count_by_type("column") == 3
        team2 = await session.get(m.TeamModel, team.id)
        cfg = team2.board_config
        assert cfg["yougile_project_id"] == "p1"
        assert cfg["synced_at"] is not None
        assert cfg["default_column_ids"] == {
            "todo": "c-todo", "in_progress": "c-prog", "done": "c-done"
        }
        # user matched to local team member by email
        umap = await repo.find_by_yougile("user", "u1")
        assert umap.local_id is not None


@pytest.mark.asyncio
async def test_discovery_bootstraps_empty_account(session_factory):
    async with session_factory() as session:
        team = await _seed_connected_team(session, member_email="nobody@example.com")
    fake = FakeYouGile(projects=[], users=[])
    res = await discover_yougile_workspace(
        session_factory, team_id=team.id, api_base_url="x", cipher=CIPHER, client=fake
    )
    assert res["ok"] is True
    assert len(fake.created["project"]) == 1
    assert len(fake.created["board"]) == 1
    assert len(fake.created["column"]) == 3

    async with session_factory() as session:
        team2 = await session.get(m.TeamModel, team.id)
        cfg = team2.board_config
        assert cfg["default_board_id"]
        assert set(cfg["default_column_ids"]) == {"todo", "in_progress", "done"}
