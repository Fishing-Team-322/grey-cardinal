"""Organization (team/workspace) management.

Endpoints:
  POST   /api/organizations              — create org (current user becomes owner)
  GET    /api/organizations/me           — org where current user is member/owner
  GET    /api/organizations/{id}         — org details
  PATCH  /api/organizations/{id}         — update org (owner only)
  DELETE /api/organizations/{id}         — delete org (owner only)
  GET    /api/organizations/{id}/members — list members + pending invites
  POST   /api/organizations/{id}/invite  — invite user by email
  DELETE /api/organizations/{id}/members/{member_id} — remove member (owner/admin)
  POST   /api/organizations/join/{token} — join org via invite token
"""

from __future__ import annotations

import logging
import re
import secrets
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.infrastructure.db.models import (
    OrganizationMemberModel,
    OrganizationModel,
    UserModel,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/organizations", tags=["organizations"])

_SLUG_RE = re.compile(r"^[a-z0-9\-_]{2,60}$")


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateOrgRequest(BaseModel):
    name: str
    slug: str
    description: str = ""

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: str) -> str:
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError("Slug must be 2–60 chars: lowercase letters, digits, - _")
        return v


class UpdateOrgRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    photo_data_url: str | None = None


class InviteRequest(BaseModel):
    email: str
    role: str = "member"

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v:
            raise ValueError("Invalid email")
        return v

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str) -> str:
        allowed = {"member", "admin", "operator", "daemon_maintainer"}
        if v not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(sorted(allowed))}")
        return v


class MemberResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    role: str
    status: str
    invited_email: str | None
    display_name: str | None
    email: str | None
    photo_data_url: str | None

    model_config = {"from_attributes": True}


class OrgResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str
    photo_data_url: str
    owner_id: UUID
    member_count: int = 0
    pending_invites: int = 0

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_org_or_404(org_id: UUID, session: AsyncSession) -> OrganizationModel:
    result = await session.execute(
        select(OrganizationModel).where(OrganizationModel.id == org_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


async def _require_owner(org: OrganizationModel, user: UserModel) -> None:
    if org.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can do this")


async def _require_owner_or_admin(
    org: OrganizationModel, user: UserModel, session: AsyncSession
) -> None:
    if org.owner_id == user.id:
        return
    result = await session.execute(
        select(OrganizationMemberModel).where(
            OrganizationMemberModel.organization_id == org.id,
            OrganizationMemberModel.user_id == user.id,
            OrganizationMemberModel.role.in_(["admin"]),
            OrganizationMemberModel.status == "active",
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


async def _build_org_response(org: OrganizationModel, session: AsyncSession) -> OrgResponse:
    members_result = await session.execute(
        select(OrganizationMemberModel).where(
            OrganizationMemberModel.organization_id == org.id
        )
    )
    members = members_result.scalars().all()
    active = sum(1 for m in members if m.status == "active")
    pending = sum(1 for m in members if m.status == "invited")
    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        description=org.description,
        photo_data_url=org.photo_data_url,
        owner_id=org.owner_id,
        member_count=active,
        pending_invites=pending,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_org(
    body: CreateOrgRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> OrgResponse:
    """Create a new organization. Current user becomes owner + active member."""
    # Check slug uniqueness
    slug_check = await session.execute(
        select(OrganizationModel).where(OrganizationModel.slug == body.slug)
    )
    if slug_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already taken",
        )

    org = OrganizationModel(
        id=uuid4(),
        name=body.name,
        slug=body.slug,
        description=body.description,
        photo_data_url="",
        owner_id=current_user.id,
    )
    session.add(org)
    await session.flush()  # get org.id before adding member

    # Owner is automatically an active member
    owner_member = OrganizationMemberModel(
        id=uuid4(),
        organization_id=org.id,
        user_id=current_user.id,
        role="owner",
        status="active",
    )
    session.add(owner_member)
    await session.commit()
    await session.refresh(org)

    logger.info("Organization created: %s (%s) by %s", org.name, org.slug, current_user.email)
    return await _build_org_response(org, session)


@router.get("/me", response_model=list[OrgResponse])
async def get_my_orgs(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> list[OrgResponse]:
    """Return all organizations where current user is an active member or owner."""
    members_result = await session.execute(
        select(OrganizationMemberModel).where(
            OrganizationMemberModel.user_id == current_user.id,
            OrganizationMemberModel.status == "active",
        )
    )
    member_rows = members_result.scalars().all()
    orgs = []
    for m in member_rows:
        org_result = await session.execute(
            select(OrganizationModel).where(OrganizationModel.id == m.organization_id)
        )
        org = org_result.scalar_one_or_none()
        if org:
            orgs.append(await _build_org_response(org, session))
    return orgs


@router.get("/{org_id}", response_model=OrgResponse)
async def get_org(
    org_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> OrgResponse:
    org = await _get_org_or_404(org_id, session)
    return await _build_org_response(org, session)


@router.patch("/{org_id}", response_model=OrgResponse)
async def update_org(
    org_id: UUID,
    body: UpdateOrgRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> OrgResponse:
    org = await _get_org_or_404(org_id, session)
    await _require_owner_or_admin(org, current_user, session)

    if body.name is not None:
        org.name = body.name.strip()
    if body.description is not None:
        org.description = body.description
    if body.photo_data_url is not None:
        org.photo_data_url = body.photo_data_url

    session.add(org)
    await session.commit()
    await session.refresh(org)
    return await _build_org_response(org, session)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(
    org_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> None:
    org = await _get_org_or_404(org_id, session)
    await _require_owner(org, current_user)

    await session.execute(
        delete(OrganizationMemberModel).where(
            OrganizationMemberModel.organization_id == org_id
        )
    )
    await session.delete(org)
    await session.commit()


@router.get("/{org_id}/members", response_model=list[MemberResponse])
async def list_members(
    org_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> list[MemberResponse]:
    await _get_org_or_404(org_id, session)
    members_result = await session.execute(
        select(OrganizationMemberModel).where(
            OrganizationMemberModel.organization_id == org_id,
            OrganizationMemberModel.status.in_(["active", "invited"]),
        )
    )
    members = members_result.scalars().all()
    result = []
    for m in members:
        user = None
        if m.user_id:
            u_result = await session.execute(
                select(UserModel).where(UserModel.id == m.user_id)
            )
            user = u_result.scalar_one_or_none()
        result.append(
            MemberResponse(
                id=m.id,
                user_id=m.user_id,
                role=m.role,
                status=m.status,
                invited_email=m.invited_email,
                display_name=user.display_name if user else None,
                email=user.email if user else m.invited_email,
                photo_data_url=user.photo_data_url if user else None,
            )
        )
    return result


@router.post("/{org_id}/invite", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    org_id: UUID,
    body: InviteRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> MemberResponse:
    """Invite a user by email. If they already have an account, mark them active."""
    org = await _get_org_or_404(org_id, session)
    await _require_owner_or_admin(org, current_user, session)

    # Check if email is already a member
    existing_user_result = await session.execute(
        select(UserModel).where(UserModel.email == body.email)
    )
    invited_user = existing_user_result.scalar_one_or_none()

    if invited_user:
        # Check not already a member
        existing_member = await session.execute(
            select(OrganizationMemberModel).where(
                OrganizationMemberModel.organization_id == org_id,
                OrganizationMemberModel.user_id == invited_user.id,
            )
        )
        if existing_member.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member",
            )

    invite_token = secrets.token_urlsafe(32)
    member = OrganizationMemberModel(
        id=uuid4(),
        organization_id=org_id,
        user_id=invited_user.id if invited_user else None,
        role=body.role,
        status="invited",
        invited_email=body.email,
        invite_token=invite_token,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)

    logger.info("Invited %s to org %s (token=%s...)", body.email, org_id, invite_token[:8])
    return MemberResponse(
        id=member.id,
        user_id=member.user_id,
        role=member.role,
        status=member.status,
        invited_email=member.invited_email,
        display_name=invited_user.display_name if invited_user else None,
        email=body.email,
        photo_data_url=invited_user.photo_data_url if invited_user else None,
    )


@router.post("/join/{invite_token}", response_model=OrgResponse)
async def join_org(
    invite_token: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> OrgResponse:
    """Accept an invite and join the organization."""
    member_result = await session.execute(
        select(OrganizationMemberModel).where(
            OrganizationMemberModel.invite_token == invite_token,
            OrganizationMemberModel.status == "invited",
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invite token",
        )

    # Link to the current user
    member.user_id = current_user.id
    member.status = "active"
    member.invite_token = None  # consume token
    session.add(member)
    await session.commit()

    org = await _get_org_or_404(member.organization_id, session)
    logger.info("User %s joined org %s", current_user.email, org.slug)
    return await _build_org_response(org, session)


@router.delete("/{org_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: UUID,
    member_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> None:
    org = await _get_org_or_404(org_id, session)
    await _require_owner_or_admin(org, current_user, session)

    member_result = await session.execute(
        select(OrganizationMemberModel).where(
            OrganizationMemberModel.id == member_id,
            OrganizationMemberModel.organization_id == org_id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.user_id == org.owner_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the owner")

    await session.delete(member)
    await session.commit()
