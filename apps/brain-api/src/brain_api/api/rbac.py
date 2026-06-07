"""RBAC helpers for the v2 tenant model."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.infrastructure.db import models as m


@dataclass(frozen=True)
class TenantContext:
    user_id: UUID
    company_roles: dict[UUID, str]
    team_roles: dict[UUID, str]


async def build_tenant_context(user_id: UUID, session: AsyncSession) -> TenantContext:
    company_rows = await session.execute(
        select(m.CompanyAdminModel).where(m.CompanyAdminModel.user_id == user_id)
    )
    team_rows = await session.execute(
        select(m.TeamMemberModel).where(m.TeamMemberModel.user_id == user_id)
    )
    return TenantContext(
        user_id=user_id,
        company_roles={row.company_id: row.role for row in company_rows.scalars().all()},
        team_roles={row.team_id: row.role for row in team_rows.scalars().all()},
    )


def require_company_role(ctx: TenantContext, company_id: UUID, role: str) -> None:
    if ctx.company_roles.get(company_id) != role:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient company permissions")


def require_team_member(ctx: TenantContext, team_id: UUID) -> None:
    if team_id not in ctx.team_roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Team membership required")


def require_team_role(ctx: TenantContext, team_id: UUID, role: str) -> None:
    if ctx.team_roles.get(team_id) != role:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient team permissions")
