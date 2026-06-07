from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from brain_api.api.routes.v2_tenants import (
    InviteCreateRequest,
    MeetingCreateRequest,
    create_company_invite,
    create_team_meeting,
)
from brain_api.infrastructure.db import models as m


async def _seed_company_team(session, *, suffix: str = ""):
    director = m.UserModel(id=uuid4(), display_name=f"Director{suffix}")
    manager = m.UserModel(id=uuid4(), display_name=f"Manager{suffix}")
    employee = m.UserModel(id=uuid4(), display_name=f"Employee{suffix}")
    company = m.CompanyModel(
        id=uuid4(), name=f"Company{suffix}", timezone="Europe/Moscow", created_by=director.id
    )
    team = m.TeamModel(
        id=uuid4(),
        company_id=company.id,
        name=f"Team{suffix}",
        timezone="Europe/Moscow",
        board_provider="mock",
    )
    session.add_all([director, manager, employee, company, team])
    await session.flush()
    session.add_all(
        [
            m.CompanyAdminModel(
                id=uuid4(), company_id=company.id, user_id=director.id, role="director"
            ),
            m.TeamMemberModel(
                id=uuid4(), team_id=team.id, user_id=manager.id, role="manager"
            ),
            m.TeamMemberModel(
                id=uuid4(), team_id=team.id, user_id=employee.id, role="employee"
            ),
        ]
    )
    await session.commit()
    return director, manager, employee, company, team


@pytest.mark.asyncio
async def test_manager_can_invite_employee_to_own_team(session_factory):
    async with session_factory() as session:
        _, manager, _, company, team = await _seed_company_team(session)

        result = await create_company_invite(
            company.id,
            InviteCreateRequest(scope="team", team_id=team.id, role="employee"),
            manager,
            session,
        )

    assert result["token"]


@pytest.mark.asyncio
async def test_manager_cannot_invite_another_manager(session_factory):
    async with session_factory() as session:
        _, manager, _, company, team = await _seed_company_team(session)

        with pytest.raises(HTTPException) as exc:
            await create_company_invite(
                company.id,
                InviteCreateRequest(scope="team", team_id=team.id, role="manager"),
                manager,
                session,
            )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_team_invite_cannot_cross_company_boundary(session_factory):
    async with session_factory() as session:
        director, _, _, company, _ = await _seed_company_team(session, suffix="A")
        _, _, _, _, foreign_team = await _seed_company_team(session, suffix="B")

        with pytest.raises(HTTPException) as exc:
            await create_company_invite(
                company.id,
                InviteCreateRequest(scope="team", team_id=foreign_team.id, role="employee"),
                director,
                session,
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_employee_cannot_schedule_meeting(session_factory):
    async with session_factory() as session:
        _, _, employee, _, team = await _seed_company_team(session)

        with pytest.raises(HTTPException) as exc:
            await create_team_meeting(
                team.id,
                MeetingCreateRequest(
                    title="Employee meeting",
                    scheduled_at=datetime.now(UTC) + timedelta(hours=1),
                ),
                employee,
                session,
            )

    assert exc.value.status_code == 403

