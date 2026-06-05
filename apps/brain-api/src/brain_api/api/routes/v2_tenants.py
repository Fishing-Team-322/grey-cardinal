"""V2 company/team APIs."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.rbac import (
    build_tenant_context,
    require_company_role,
    require_team_member,
    require_team_role,
)
from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.config import get_settings
from brain_api.domain.v2.timezones import validate_iana_timezone
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher

router = APIRouter(tags=["v2-tenants"])


class CompanyCreateRequest(BaseModel):
    name: str = Field(min_length=2)
    timezone: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class CompanyResponse(BaseModel):
    id: UUID
    name: str
    timezone: str
    role: str | None = None


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=2)
    timezone: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class TeamResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    timezone: str
    role: str | None = None
    tg_chat_id: int | None = None


class InviteCreateRequest(BaseModel):
    scope: str = "team"
    team_id: UUID | None = None
    role: str = "employee"
    expires_hours: int = 72
    max_uses: int = 1


class BoardConfigRequest(BaseModel):
    provider: str = "yougile"
    credentials: dict
    config: dict = Field(default_factory=dict)


class LLMSettingsRequest(BaseModel):
    provider: str
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: int = 20
    max_retries: int = 2
    strict_json: bool = True
    enabled: bool = True


@router.post("/api/companies", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    settings = get_settings()
    existing = await session.scalar(
        select(m.CompanyAdminModel).where(m.CompanyAdminModel.user_id == current_user.id)
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "User already belongs to a company in v2")

    if body.timezone is None:
        if settings.is_production:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Выберите часовой пояс компании"
            )
        timezone = validate_iana_timezone(settings.default_timezone)
    else:
        timezone = validate_iana_timezone(body.timezone)

    company = m.CompanyModel(
        id=uuid4(), name=body.name, timezone=timezone, created_by=current_user.id
    )
    admin = m.CompanyAdminModel(
        id=uuid4(), company_id=company.id, user_id=current_user.id, role="director"
    )
    session.add_all([company, admin])
    await session.commit()
    return CompanyResponse(
        id=company.id, name=company.name, timezone=company.timezone, role="director"
    )


@router.get("/api/companies/me", response_model=list[CompanyResponse])
async def my_companies(
    current_user: CurrentUser, session: AsyncSession = Depends(get_db)
) -> list[CompanyResponse]:
    rows = await session.execute(
        select(m.CompanyModel, m.CompanyAdminModel.role)
        .join(m.CompanyAdminModel, m.CompanyAdminModel.company_id == m.CompanyModel.id)
        .where(m.CompanyAdminModel.user_id == current_user.id)
    )
    return [
        CompanyResponse(id=company.id, name=company.name, timezone=company.timezone, role=role)
        for company, role in rows.all()
    ]


@router.get("/api/me")
async def me(current_user: CurrentUser, session: AsyncSession = Depends(get_db)) -> dict:
    companies = await my_companies(current_user, session)
    team_rows = await session.execute(
        select(m.TeamModel, m.TeamMemberModel.role)
        .join(m.TeamMemberModel, m.TeamMemberModel.team_id == m.TeamModel.id)
        .where(m.TeamMemberModel.user_id == current_user.id)
    )
    teams = [
        TeamResponse(
            id=team.id,
            company_id=team.company_id,
            name=team.name,
            timezone=team.timezone,
            role=role,
            tg_chat_id=team.tg_chat_id,
        ).model_dump(mode="json")
        for team, role in team_rows.all()
    ]
    return {
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "display_name": current_user.display_name,
            "telegram_user_id": current_user.telegram_user_id,
            "timezone": current_user.timezone,
        },
        "companies": [item.model_dump(mode="json") for item in companies],
        "teams": teams,
    }


@router.post(
    "/api/companies/{company_id}/teams",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_team(
    company_id: UUID,
    body: TeamCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> TeamResponse:
    ctx = await build_tenant_context(current_user.id, session)
    require_company_role(ctx, company_id, "director")
    company = await session.get(m.CompanyModel, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    timezone = validate_iana_timezone(body.timezone) if body.timezone else company.timezone
    team = m.TeamModel(
        id=uuid4(),
        company_id=company_id,
        name=body.name,
        timezone=timezone,
        board_provider="yougile",
    )
    manager = m.TeamMemberModel(
        id=uuid4(), team_id=team.id, user_id=current_user.id, role="manager"
    )
    session.add_all([team, manager])
    await session.commit()
    return TeamResponse(
        id=team.id,
        company_id=team.company_id,
        name=team.name,
        timezone=team.timezone,
        role="manager",
        tg_chat_id=team.tg_chat_id,
    )


@router.get("/api/teams/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_db)
) -> TeamResponse:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_member(ctx, team_id)
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    return TeamResponse(
        id=team.id,
        company_id=team.company_id,
        name=team.name,
        timezone=team.timezone,
        role=ctx.team_roles.get(team.id),
        tg_chat_id=team.tg_chat_id,
    )


@router.post("/api/companies/{company_id}/invites", status_code=status.HTTP_201_CREATED)
async def create_company_invite(
    company_id: UUID,
    body: InviteCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    ctx = await build_tenant_context(current_user.id, session)
    require_company_role(ctx, company_id, "director")
    if body.scope not in {"company", "team"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid invite scope")
    if body.role not in {"director", "manager", "employee"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid invite role")
    token = secrets.token_urlsafe(32)
    invite = m.InviteModel(
        id=uuid4(),
        token=token,
        scope=body.scope,
        company_id=company_id,
        team_id=body.team_id,
        role=body.role,
        created_by=current_user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=body.expires_hours),
        max_uses=body.max_uses,
        uses=0,
    )
    session.add(invite)
    await session.commit()
    return {"token": token, "expires_at": invite.expires_at}


@router.get("/api/companies/{company_id}/overview")
async def company_overview(
    company_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    ctx = await build_tenant_context(current_user.id, session)
    require_company_role(ctx, company_id, "director")
    company = await session.get(m.CompanyModel, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    team_rows = (
        (await session.execute(select(m.TeamModel).where(m.TeamModel.company_id == company_id)))
        .scalars()
        .all()
    )
    team_payload: list[dict[str, Any]] = []
    total_open = total_overdue = total_done = 0
    now = datetime.now(UTC)
    for team in team_rows:
        members_count = await session.scalar(
            select(func.count())
            .select_from(m.TeamMemberModel)
            .where(m.TeamMemberModel.team_id == team.id)
        )
        open_tasks = await session.scalar(
            select(func.count())
            .select_from(m.V2TaskModel)
            .where(
                m.V2TaskModel.team_id == team.id,
                m.V2TaskModel.status.notin_(["done", "cancelled"]),
            )
        )
        overdue = await session.scalar(
            select(func.count())
            .select_from(m.V2TaskModel)
            .where(
                m.V2TaskModel.team_id == team.id,
                m.V2TaskModel.deadline.is_not(None),
                m.V2TaskModel.deadline < now,
                m.V2TaskModel.status.notin_(["done", "cancelled"]),
            )
        )
        completed_7d = await session.scalar(
            select(func.count())
            .select_from(m.V2TaskModel)
            .where(
                m.V2TaskModel.team_id == team.id,
                m.V2TaskModel.completed_at >= now - timedelta(days=7),
            )
        )
        total_open += int(open_tasks or 0)
        total_overdue += int(overdue or 0)
        total_done += int(completed_7d or 0)
        team_payload.append(
            {
                "id": str(team.id),
                "name": team.name,
                "timezone": team.timezone,
                "members_count": int(members_count or 0),
                "open_tasks": int(open_tasks or 0),
                "overdue_tasks": int(overdue or 0),
                "sync_rate_7d": 0.0,
                "completed_last_7_days": int(completed_7d or 0),
                "last_activity_at": None,
            }
        )
    hotspots = [
        {
            "team_id": item["id"],
            "kind": "overdue",
            "message": f"В команде {item['name']} {item['overdue_tasks']} просроченные задачи",
        }
        for item in team_payload
        if int(item["overdue_tasks"]) > 0
    ]
    return {
        "company": {"id": str(company.id), "name": company.name, "timezone": company.timezone},
        "totals": {
            "teams": len(team_payload),
            "open_tasks": total_open,
            "overdue_tasks": total_overdue,
            "completed_last_7_days": total_done,
        },
        "teams": team_payload,
        "hotspots": hotspots,
    }


@router.post("/api/teams/{team_id}/board")
async def set_team_board(
    team_id: UUID,
    body: BoardConfigRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    if body.provider != "yougile":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only YouGile is supported in v2")
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, team_id, "manager")
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    cipher = SecretCipher(get_settings().board_creds_encryption_key or "dev-key")
    team.board_provider = body.provider
    team.board_credentials_encrypted = cipher.encrypt_text(json.dumps(body.credentials))
    team.board_config = body.config
    session.add(team)
    await session.commit()
    return {"status": "configured", "provider": body.provider}


@router.delete("/api/teams/{team_id}/board", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team_board(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> None:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, team_id, "manager")
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    team.board_credentials_encrypted = None
    team.board_config = None
    session.add(team)
    await session.commit()


@router.get("/api/teams/{team_id}/board/status")
async def team_board_status(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_member(ctx, team_id)
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    configured = bool(team.board_credentials_encrypted and team.board_config)
    return {
        "provider": team.board_provider,
        "configured": configured,
        "status": "ok" if configured else "failed",
        "error": None if configured else "YouGile credentials are not configured for this team",
    }


@router.post("/api/teams/{team_id}/llm-settings", status_code=status.HTTP_201_CREATED)
async def set_team_llm_settings(
    team_id: UUID,
    body: LLMSettingsRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    if body.provider not in {"local", "external_api"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid LLM provider")
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, team_id, "manager")
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    cipher = SecretCipher(get_settings().board_creds_encryption_key or "dev-key")
    existing = await session.scalar(
        select(m.LLMSettingsModel).where(m.LLMSettingsModel.team_id == team_id)
    )
    row = existing or m.LLMSettingsModel(id=uuid4(), company_id=team.company_id, team_id=team_id)
    row.provider = body.provider
    row.base_url = body.base_url
    row.model = body.model
    row.api_key_encrypted = cipher.encrypt_text(body.api_key) if body.api_key else None
    row.timeout_seconds = body.timeout_seconds
    row.max_retries = body.max_retries
    row.strict_json = body.strict_json
    row.enabled = body.enabled
    session.add(row)
    await session.flush()
    team.llm_settings_id = row.id
    session.add(team)
    await session.commit()
    return {
        "id": str(row.id),
        "provider": row.provider,
        "base_url": row.base_url,
        "model": row.model,
    }


@router.get("/api/teams/{team_id}/llm-settings")
async def get_team_llm_settings(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, team_id, "manager")
    row = await session.scalar(
        select(m.LLMSettingsModel).where(m.LLMSettingsModel.team_id == team_id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "LLM settings not found")
    return {
        "id": str(row.id),
        "provider": row.provider,
        "base_url": row.base_url,
        "model": row.model,
        "timeout_seconds": row.timeout_seconds,
        "max_retries": row.max_retries,
        "strict_json": row.strict_json,
        "enabled": row.enabled,
    }


@router.delete("/api/teams/{team_id}/llm-settings", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team_llm_settings(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> None:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, team_id, "manager")
    row = await session.scalar(
        select(m.LLMSettingsModel).where(m.LLMSettingsModel.team_id == team_id)
    )
    if row is not None:
        await session.delete(row)
        await session.commit()


@router.get("/api/teams/{team_id}/llm/health")
async def team_llm_health(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_role(ctx, team_id, "manager")
    return {"status": "configured"}
