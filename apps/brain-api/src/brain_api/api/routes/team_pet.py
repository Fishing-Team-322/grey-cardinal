"""Команд­ный питомец: create/rename, события, инвентарь, экипировка, privacy, батлы.

Legacy ``GET /api/teams/{team_id}/pet`` и ``GET /api/teams/{team_id}/wellbeing``
живут в grey_board.py и расширены под новый контракт. Здесь — остальные endpoints.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.rbac import build_tenant_context, require_team_member
from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.application.use_cases import team_battles as battles
from brain_api.application.use_cases import team_pet_service as svc
from brain_api.infrastructure.db import models as m

router = APIRouter(tags=["team-pet"])


# ── access helpers ───────────────────────────────────────────────────────────


async def _team_member(team_id: UUID, current_user: CurrentUser, session: AsyncSession) -> None:
    ctx = await build_tenant_context(current_user.id, session)
    require_team_member(ctx, team_id)
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")


async def _require_manager(team_id: UUID, current_user: CurrentUser, session: AsyncSession) -> None:
    """Разрешить manager команды ИЛИ director компании, к которой относится команда."""
    ctx = await build_tenant_context(current_user.id, session)
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    if ctx.team_roles.get(team_id) == "manager":
        return
    if ctx.company_roles.get(team.company_id) == "director":
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager or director role required")


# ── schemas ──────────────────────────────────────────────────────────────────


class CreatePetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    species: str = "fox"


class RenamePetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class EquipRequest(BaseModel):
    item_id: str


class PrivacyRequest(BaseModel):
    analyze_tasks: bool | None = None
    analyze_chat: bool | None = None
    analyze_calls: bool | None = None
    analyze_camera: bool | None = None
    team_aggregates_only: bool | None = None
    manager_individual_signals: bool | None = None
    retention_days: int | None = None
    visible_to: str | None = None


# ── pet create / rename ──────────────────────────────────────────────────────


@router.post("/api/teams/{team_id}/pet", status_code=status.HTTP_201_CREATED)
async def create_team_pet(
    team_id: UUID,
    body: CreatePetRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_manager(team_id, current_user, session)
    if await svc.pet_exists(session, team_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Pet already exists")
    await svc.create_pet(session, team_id, name=body.name, species=body.species)
    payload = await svc.build_pet_payload(session, team_id)
    await session.commit()
    return payload


@router.patch("/api/teams/{team_id}/pet")
async def rename_team_pet(
    team_id: UUID,
    body: RenamePetRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_manager(team_id, current_user, session)
    if not await svc.pet_exists(session, team_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pet not found")
    await svc.rename_pet(session, team_id, name=body.name)
    payload = await svc.build_pet_payload(session, team_id)
    await session.commit()
    return payload


# ── events ───────────────────────────────────────────────────────────────────


@router.get("/api/teams/{team_id}/pet/events")
async def team_pet_events(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    await _team_member(team_id, current_user, session)
    return await svc.list_events(session, team_id, limit=limit, cursor=cursor)


# ── inventory ────────────────────────────────────────────────────────────────


@router.get("/api/teams/{team_id}/pet/inventory")
async def team_pet_inventory(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _team_member(team_id, current_user, session)
    return await svc.list_inventory(session, team_id)


@router.post("/api/teams/{team_id}/pet/equip")
async def team_pet_equip(
    team_id: UUID,
    body: EquipRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_manager(team_id, current_user, session)
    if not await svc.pet_exists(session, team_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pet not found")
    ok, message = await svc.equip_item(session, team_id, body.item_id)
    if not ok:
        # Ветки отказа не мутируют состояние — откат не нужен.
        code = status.HTTP_404_NOT_FOUND if message == "unknown_item" else status.HTTP_409_CONFLICT
        raise HTTPException(code, message)
    inventory = await svc.list_inventory(session, team_id)
    pet = await svc.build_pet_payload(session, team_id)
    await session.commit()
    return {"ok": True, "inventory": inventory, "pet": pet}


# ── privacy ──────────────────────────────────────────────────────────────────


@router.get("/api/teams/{team_id}/pet/privacy")
async def get_team_pet_privacy(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _team_member(team_id, current_user, session)
    row = await svc.ensure_privacy(session, team_id)
    await session.commit()
    return svc.privacy_dict(row)


@router.put("/api/teams/{team_id}/pet/privacy")
async def put_team_pet_privacy(
    team_id: UUID,
    body: PrivacyRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_manager(team_id, current_user, session)
    row = await svc.update_privacy(
        session,
        team_id,
        body.model_dump(exclude_none=True),
        can_enable_sensitive=True,
    )
    await session.commit()
    return svc.privacy_dict(row)


# ── battles ──────────────────────────────────────────────────────────────────


@router.get("/api/team-battles/current")
async def current_battle(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    payload = await battles.current_battle_payload(session)
    await session.commit()
    return payload


@router.get("/api/team-battles/current/leaderboard")
async def current_battle_leaderboard(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
    team_id: UUID | None = None,
) -> dict[str, Any]:
    # team_id опционален: подсветить свою команду. Доступ — любой авторизованный.
    payload = await battles.leaderboard_payload(session, current_team_id=team_id)
    await session.commit()
    return payload
