from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from brain_api.api.routes.accounts import ChangePasswordRequest, change_password
from brain_api.api.routes.v2_tenants import (
    TaskStatusResponseRequest,
    company_leaderboard,
    list_team_members,
    list_team_tasks,
    remove_team_member,
    task_status_response,
    update_team_member_role,
    TeamMemberRoleRequest,
)
from brain_api.infrastructure.auth.jwt import hash_password, verify_password
from brain_api.infrastructure.db import models as m


class _WebSockets:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def broadcast(self, message: dict) -> None:
        self.messages.append(message)


async def _seed(session):
    director = m.UserModel(id=uuid4(), display_name="Director", email="d@example.com")
    employee = m.UserModel(id=uuid4(), display_name="Employee", email="e@example.com")
    outsider = m.UserModel(id=uuid4(), display_name="Outsider", email="o@example.com")
    company = m.CompanyModel(
        id=uuid4(), name="Company", timezone="Europe/Moscow", created_by=director.id
    )
    team = m.TeamModel(
        id=uuid4(),
        company_id=company.id,
        name="Core",
        timezone="Europe/Moscow",
        board_provider="mock",
    )
    session.add_all([director, employee, outsider, company, team])
    await session.flush()
    session.add_all(
        [
            m.CompanyAdminModel(
                id=uuid4(), company_id=company.id, user_id=director.id, role="director"
            ),
            m.TeamMemberModel(
                id=uuid4(), team_id=team.id, user_id=director.id, role="manager"
            ),
            m.TeamMemberModel(
                id=uuid4(), team_id=team.id, user_id=employee.id, role="employee"
            ),
        ]
    )
    task = m.TaskModel(
        id=uuid4(),
        seq=9001,
        public_id="GC-9001",
        team_id=team.id,
        title="Frontend contract",
        status="todo",
        priority="medium",
        assignee_id=employee.id,
        source="manual",
    )
    session.add(task)
    await session.commit()
    return director, employee, outsider, company, team, task


@pytest.mark.asyncio
async def test_members_and_tasks_are_tenant_scoped(session_factory):
    async with session_factory() as session:
        director, employee, outsider, _, team, _ = await _seed(session)
        session.add(
            m.DeviceModel(
                id=uuid4(),
                user_id=employee.id,
                device_name="Employee PC",
                platform="windows",
                last_seen_at=datetime.now(UTC),
            )
        )
        await session.commit()
        members = await list_team_members(team.id, employee, session)
        tasks = await list_team_tasks(team.id, employee, None, "me", session)
        with pytest.raises(HTTPException) as exc:
            await list_team_members(team.id, outsider, session)

    assert {item["role"] for item in members["items"]} == {"manager", "employee"}
    assert any(item["online"] and item["last_seen_at"] for item in members["items"])
    assert tasks["items"][0]["assignee_id"] == str(employee.id)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_director_can_manage_team_member_roles(session_factory):
    async with session_factory() as session:
        director, employee, _, _, team, _ = await _seed(session)

        promoted = await update_team_member_role(
            team.id,
            employee.id,
            TeamMemberRoleRequest(role="manager"),
            director,
            session,
        )
        removed = await remove_team_member(team.id, employee.id, director, session)
        members = await list_team_members(team.id, director, session)

    assert promoted["role"] == "manager"
    assert removed is None
    assert {item["id"] for item in members["items"]} == {str(director.id)}


@pytest.mark.asyncio
async def test_employee_can_update_own_task_and_get_xp(session_factory):
    sockets = _WebSockets()
    container = SimpleNamespace(websocket_manager=sockets)
    async with session_factory() as session:
        _, employee, _, _, _, task = await _seed(session)
        result = await task_status_response(
            task.id,
            TaskStatusResponseRequest(response="done"),
            employee,
            container,
            session,
        )

        assert result["status"] == "done"
        assert sockets.messages[0]["event"] == "task_status_responded"
        xp = await session.scalar(
            select(m.UserXpTotalModel).where(m.UserXpTotalModel.user_id == employee.id)
        )
        assert xp is not None


@pytest.mark.asyncio
async def test_company_leaderboard_requires_director(session_factory):
    async with session_factory() as session:
        director, employee, _, company, _, _ = await _seed(session)
        result = await company_leaderboard(company.id, director, session)
        with pytest.raises(HTTPException) as exc:
            await company_leaderboard(company.id, employee, session)

    assert result["company_name"] == "Company"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_change_password_validates_current_password(session_factory):
    async with session_factory() as session:
        user = m.UserModel(
            id=uuid4(),
            display_name="Account",
            email="account@example.com",
            password_hash=hash_password("old-secret"),
        )
        session.add(user)
        await session.commit()
        await change_password(
            ChangePasswordRequest(old_password="old-secret", new_password="new-secret"),
            user,
            session,
        )
        assert verify_password("new-secret", user.password_hash)
