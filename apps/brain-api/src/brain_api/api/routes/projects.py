"""Production cross-team projects API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.deps import get_container
from brain_api.api.rbac import build_tenant_context
from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.application.task_numbering import next_task_public_id
from brain_api.application.use_cases.cross_team_projects import (
    build_project_draft,
    create_project_from_draft,
    project_payload,
    reconcile_project_from_yougile,
    sync_project_to_yougile,
)
from brain_api.container import Container
from brain_api.infrastructure.db import models as m

router = APIRouter(tags=["projects"])


class ProjectPreviewRequest(BaseModel):
    description: str = Field(min_length=10, max_length=12000)
    horizon_weeks: int = Field(default=6, ge=1, le=52)
    source_team_id: UUID | None = None
    team_ids: list[UUID] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        return value.strip()


class ProjectTaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    role: str | None = None
    estimated_hours: float | None = Field(default=None, ge=0, le=10000)
    owner_team_id: UUID
    team_ids: list[UUID] = Field(default_factory=list)
    assignee_ids: list[UUID] = Field(default_factory=list)
    deadline: datetime | None = None
    status: str = "todo"
    priority: str = "medium"


class ProjectCreateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=12000)
    expected_result: str | None = Field(default=None, max_length=4000)
    lead_team_id: UUID | None = None
    team_ids: list[UUID] = Field(default_factory=list)
    starts_at: datetime | None = None
    deadline: datetime | None = None
    tasks: list[ProjectTaskInput] | None = None
    sync_yougile: bool = False


class ProjectDraftPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=12000)
    expected_result: str | None = Field(default=None, max_length=4000)
    lead_team_id: UUID | None = None
    team_ids: list[UUID] | None = None
    starts_at: datetime | None = None
    deadline: datetime | None = None
    tasks: list[ProjectTaskInput] | None = None


class ProjectPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=12000)
    expected_result: str | None = Field(default=None, max_length=4000)
    status: str | None = None
    starts_at: datetime | None = None
    deadline: datetime | None = None


class ProjectTaskAssigneesRequest(BaseModel):
    user_ids: list[UUID] = Field(default_factory=list, max_length=20)


class ChatBindingRequest(BaseModel):
    telegram_chat_id: UUID
    message_thread_id: int | None = None
    kind: str = "project"


@router.post(
    "/api/companies/{company_id}/project-drafts/preview",
    status_code=status.HTTP_201_CREATED,
)
async def preview_project(
    company_id: UUID,
    body: ProjectPreviewRequest,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_company_planner(session, current_user.id, company_id)
    try:
        draft = await build_project_draft(
            session,
            company_id=company_id,
            created_by=current_user.id,
            description=body.description,
            horizon_weeks=body.horizon_weeks,
            source_team_id=body.source_team_id,
            candidate_team_ids=body.team_ids or None,
            provider_factory=container.llm_provider_factory,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _draft_payload(draft)


@router.get("/api/project-drafts/{draft_id}")
async def get_project_draft(
    draft_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    draft = await _draft_for_actor(session, draft_id, current_user.id)
    return _draft_payload(draft)


@router.patch("/api/project-drafts/{draft_id}")
async def update_project_draft(
    draft_id: UUID,
    body: ProjectDraftPatchRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    draft = await _draft_for_actor(session, draft_id, current_user.id)
    payload = dict(draft.payload or {})
    changes = body.model_dump(mode="json", exclude_none=True)
    if "name" in changes:
        draft.generated_name = changes["name"].strip()
    payload.update(changes)
    draft.payload = payload
    draft.version += 1
    session.add(draft)
    await session.commit()
    await session.refresh(draft)
    return _draft_payload(draft)


@router.post("/api/project-drafts/{draft_id}/create", status_code=status.HTTP_201_CREATED)
async def create_project(
    draft_id: UUID,
    body: ProjectCreateRequest,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    draft = await _draft_for_actor(session, draft_id, current_user.id)
    payload = draft.payload or {}
    lead_team_id = body.lead_team_id or UUID(str(payload["lead_team_id"]))
    await _require_project_creator(
        session,
        current_user.id,
        draft.company_id,
        lead_team_id,
    )
    try:
        project = await create_project_from_draft(
            session,
            draft=draft,
            actor_id=current_user.id,
            name=body.name,
            description=body.description,
            expected_result=body.expected_result,
            lead_team_id=lead_team_id,
            team_ids=body.team_ids or None,
            starts_at=body.starts_at,
            deadline=body.deadline,
            tasks=[item.model_dump(mode="json") for item in body.tasks] if body.tasks else None,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    sync = None
    if body.sync_yougile:
        sync = await sync_project_to_yougile(
            session,
            project_id=project.id,
            source_team_id=lead_team_id,
            settings=container.settings,
        )
        await session.refresh(project)
    result = await project_payload(session, project)
    result["yougile_sync"] = sync
    return result


@router.get("/api/projects")
async def my_projects(
    current_user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ctx = await build_tenant_context(current_user.id, session)
    company_ids = set(ctx.company_roles)
    if ctx.team_roles:
        rows = await session.scalars(
            select(m.TeamModel.company_id).where(m.TeamModel.id.in_(ctx.team_roles))
        )
        company_ids.update(rows)
    if not company_ids:
        return {"items": []}
    statement = (
        select(m.CompanyProjectModel)
        .where(m.CompanyProjectModel.company_id.in_(company_ids))
        .order_by(m.CompanyProjectModel.updated_at.desc())
    )
    if status_filter:
        statement = statement.where(m.CompanyProjectModel.status == status_filter)
    projects = list(await session.scalars(statement.limit(200)))
    visible = [
        project for project in projects
        if await _can_view_project(session, current_user.id, project)
    ]
    return {"items": [await project_payload(session, project) for project in visible]}


@router.get("/api/companies/{company_id}/projects")
async def company_projects(
    company_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _require_company_planner(session, current_user.id, company_id)
    projects = list(
        await session.scalars(
            select(m.CompanyProjectModel)
            .where(m.CompanyProjectModel.company_id == company_id)
            .order_by(m.CompanyProjectModel.updated_at.desc())
        )
    )
    return {"items": [await project_payload(session, project) for project in projects]}


@router.get("/api/teams/{team_id}/projects")
async def team_projects(
    team_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ctx = await build_tenant_context(current_user.id, session)
    team = await session.get(m.TeamModel, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    if team_id not in ctx.team_roles and ctx.company_roles.get(team.company_id) != "director":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Team access required")
    projects = list(
        await session.scalars(
            select(m.CompanyProjectModel)
            .join(m.ProjectTeamModel, m.ProjectTeamModel.project_id == m.CompanyProjectModel.id)
            .where(
                m.ProjectTeamModel.team_id == team_id,
                m.ProjectTeamModel.participation_status == "active",
            )
            .order_by(m.CompanyProjectModel.updated_at.desc())
        )
    )
    return {"items": [await project_payload(session, project) for project in projects]}


@router.get("/api/projects/{project_id}")
async def get_project(
    project_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await _project_for_user(session, project_id, current_user.id)
    return await project_payload(session, project)


@router.patch("/api/projects/{project_id}")
async def update_project(
    project_id: UUID,
    body: ProjectPatchRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await _project_for_manager(session, project_id, current_user.id)
    if body.status and body.status not in {"active", "paused", "completed", "cancelled"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid project status")
    for field in ("name", "description", "expected_result", "status", "starts_at", "deadline"):
        value = getattr(body, field)
        if value is not None:
            setattr(project, field, value)
    session.add(project)
    session.add(
        m.AuditLogModel(
            id=uuid4(),
            actor_type="user",
            actor_id=str(current_user.id),
            action="cross_team_project_updated",
            entity_type="company_project",
            entity_id=project.id,
            payload=body.model_dump(mode="json", exclude_none=True),
        )
    )
    await session.commit()
    await session.refresh(project)
    return await project_payload(session, project)


@router.post("/api/projects/{project_id}/yougile/sync")
async def sync_project(
    project_id: UUID,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await _project_for_manager(session, project_id, current_user.id)
    lead_team_id = await session.scalar(
        select(m.ProjectTeamModel.team_id).where(
            m.ProjectTeamModel.project_id == project.id,
            m.ProjectTeamModel.role == "lead",
        )
    )
    if lead_team_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Project lead team is not configured")
    return await sync_project_to_yougile(
        session,
        project_id=project.id,
        source_team_id=lead_team_id,
        settings=container.settings,
    )


@router.post("/api/projects/{project_id}/yougile/pull")
async def pull_project_from_yougile(
    project_id: UUID,
    current_user: CurrentUser,
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reflect YouGile-side changes (task moved between columns) back onto the
    site. Any project member can trigger it; it only reads YouGile and updates
    local task statuses."""
    project = await _project_for_user(session, project_id, current_user.id)
    result = await reconcile_project_from_yougile(
        session, project=project, settings=container.settings
    )
    payload = await project_payload(session, project)
    return {**result, "project": payload}


@router.post("/api/projects/{project_id}/tasks", status_code=status.HTTP_201_CREATED)
async def create_project_task(
    project_id: UUID,
    body: ProjectTaskInput,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await _project_for_manager(session, project_id, current_user.id)
    project_team_ids = set(
        await session.scalars(
            select(m.ProjectTeamModel.team_id).where(
                m.ProjectTeamModel.project_id == project.id,
                m.ProjectTeamModel.participation_status == "active",
            )
        )
    )
    task_team_ids = set(body.team_ids) | {body.owner_team_id}
    if body.owner_team_id not in project_team_ids or not task_team_ids.issubset(project_team_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Task teams must belong to project",
        )
    member_ids = set(
        await session.scalars(
            select(m.ProjectMemberModel.user_id).where(
                m.ProjectMemberModel.project_id == project.id,
                m.ProjectMemberModel.active.is_(True),
            )
        )
    )
    if not set(body.assignee_ids).issubset(member_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Assignees must belong to project",
        )
    if body.status not in {"todo", "in_progress", "blocked", "review", "done", "cancelled"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid task status")
    seq, public_id = await next_task_public_id(session, body.owner_team_id)
    task = m.TaskModel(
        id=uuid4(),
        seq=seq,
        public_id=public_id,
        company_project_id=project.id,
        team_id=body.owner_team_id,
        title=body.title.strip(),
        description=body.description,
        status=body.status,
        priority=body.priority,
        assignee_id=body.assignee_ids[0] if body.assignee_ids else None,
        deadline=body.deadline,
        source="project",
        source_type="project",
    )
    session.add(task)
    await session.flush()
    for team_id in task_team_ids:
        session.add(
            m.TaskTeamModel(
                id=uuid4(),
                task_id=task.id,
                team_id=team_id,
                role="owner" if team_id == body.owner_team_id else "contributor",
            )
        )
    for index, user_id in enumerate(body.assignee_ids):
        session.add(
            m.TaskAssigneeModel(
                id=uuid4(),
                task_id=task.id,
                user_id=user_id,
                role="owner" if index == 0 else "contributor",
            )
        )
    await session.commit()
    return await project_payload(session, project)


@router.put("/api/projects/{project_id}/tasks/{task_id}/assignees")
async def set_project_task_assignees(
    project_id: UUID,
    task_id: UUID,
    body: ProjectTaskAssigneesRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await _project_for_manager(session, project_id, current_user.id)
    task = await session.get(m.TaskModel, task_id)
    if task is None or task.company_project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    member_ids = set(
        await session.scalars(
            select(m.ProjectMemberModel.user_id).where(
                m.ProjectMemberModel.project_id == project.id,
                m.ProjectMemberModel.active.is_(True),
            )
        )
    )
    if not set(body.user_ids).issubset(member_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Assignees must belong to project",
        )
    existing = list(
        await session.scalars(
            select(m.TaskAssigneeModel).where(m.TaskAssigneeModel.task_id == task.id)
        )
    )
    for row in existing:
        await session.delete(row)
    for index, user_id in enumerate(dict.fromkeys(body.user_ids)):
        session.add(
            m.TaskAssigneeModel(
                id=uuid4(),
                task_id=task.id,
                user_id=user_id,
                role="owner" if index == 0 else "contributor",
            )
        )
    task.assignee_id = body.user_ids[0] if body.user_ids else None
    await session.commit()
    return await project_payload(session, project)


@router.post(
    "/api/projects/{project_id}/chat-bindings",
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_binding(
    project_id: UUID,
    body: ChatBindingRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await _project_for_manager(session, project_id, current_user.id)
    chat = await session.get(m.TelegramChatModel, body.telegram_chat_id)
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram chat not found")
    if chat.team_id:
        team = await session.get(m.TeamModel, chat.team_id)
        if team is None or team.company_id != project.company_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Chat belongs to another company",
            )
    conflict = await session.scalar(
        select(m.ProjectChatBindingModel).where(
            m.ProjectChatBindingModel.telegram_chat_id == chat.id,
            m.ProjectChatBindingModel.message_thread_id == body.message_thread_id,
        )
    )
    if conflict is not None and conflict.project_id != project.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chat context is already bound")
    binding = conflict or m.ProjectChatBindingModel(
        id=uuid4(),
        project_id=project.id,
        telegram_chat_id=chat.id,
        message_thread_id=body.message_thread_id,
        kind=body.kind,
        created_by=current_user.id,
    )
    session.add(binding)
    await session.commit()
    return {
        "id": str(binding.id),
        "project_id": str(binding.project_id),
        "telegram_chat_id": str(binding.telegram_chat_id),
        "message_thread_id": binding.message_thread_id,
        "kind": binding.kind,
    }


@router.delete(
    "/api/projects/{project_id}/chat-bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat_binding(
    project_id: UUID,
    binding_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> None:
    await _project_for_manager(session, project_id, current_user.id)
    binding = await session.get(m.ProjectChatBindingModel, binding_id)
    if binding is None or binding.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat binding not found")
    await session.delete(binding)
    await session.commit()


async def _require_company_planner(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> None:
    ctx = await build_tenant_context(user_id, session)
    if ctx.company_roles.get(company_id) == "director":
        return
    managed = await session.scalar(
        select(m.TeamMemberModel.id)
        .join(m.TeamModel, m.TeamModel.id == m.TeamMemberModel.team_id)
        .where(
            m.TeamMemberModel.user_id == user_id,
            m.TeamMemberModel.role == "manager",
            m.TeamModel.company_id == company_id,
        )
        .limit(1)
    )
    if managed is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager or director role required")


async def _require_project_creator(
    session: AsyncSession,
    user_id: UUID,
    company_id: UUID,
    lead_team_id: UUID,
) -> None:
    ctx = await build_tenant_context(user_id, session)
    if ctx.company_roles.get(company_id) == "director":
        return
    if ctx.team_roles.get(lead_team_id) != "manager":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Manager must lead the project with a managed team",
        )


async def _draft_for_actor(
    session: AsyncSession, draft_id: UUID, user_id: UUID
) -> m.CompanyProjectDraftModel:
    draft = await session.get(m.CompanyProjectDraftModel, draft_id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project draft not found")
    await _require_company_planner(session, user_id, draft.company_id)
    if draft.created_by != user_id:
        ctx = await build_tenant_context(user_id, session)
        if ctx.company_roles.get(draft.company_id) != "director":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Draft owner or director required")
    return draft


async def _project_for_user(
    session: AsyncSession, project_id: UUID, user_id: UUID
) -> m.CompanyProjectModel:
    project = await session.get(m.CompanyProjectModel, project_id)
    if project is None or not await _can_view_project(session, user_id, project):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


async def _can_view_project(
    session: AsyncSession, user_id: UUID, project: m.CompanyProjectModel
) -> bool:
    ctx = await build_tenant_context(user_id, session)
    if ctx.company_roles.get(project.company_id) == "director":
        return True
    if await session.scalar(
        select(m.ProjectMemberModel.id).where(
            m.ProjectMemberModel.project_id == project.id,
            m.ProjectMemberModel.user_id == user_id,
            m.ProjectMemberModel.active.is_(True),
        )
    ):
        return True
    project_team_ids = select(m.ProjectTeamModel.team_id).where(
        m.ProjectTeamModel.project_id == project.id,
        m.ProjectTeamModel.participation_status == "active",
    )
    return any(team_id in ctx.team_roles for team_id in await session.scalars(project_team_ids))


async def _project_for_manager(
    session: AsyncSession, project_id: UUID, user_id: UUID
) -> m.CompanyProjectModel:
    project = await _project_for_user(session, project_id, user_id)
    ctx = await build_tenant_context(user_id, session)
    if ctx.company_roles.get(project.company_id) == "director":
        return project
    managed_team_ids = {
        team_id for team_id, role in ctx.team_roles.items() if role == "manager"
    }
    project_team_ids = set(
        await session.scalars(
            select(m.ProjectTeamModel.team_id).where(
                m.ProjectTeamModel.project_id == project.id
            )
        )
    )
    if not managed_team_ids.intersection(project_team_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project manager role required")
    return project


def _draft_payload(draft: m.CompanyProjectDraftModel) -> dict[str, Any]:
    return {
        "id": str(draft.id),
        "company_id": str(draft.company_id),
        "created_by": str(draft.created_by),
        "source_team_id": str(draft.source_team_id) if draft.source_team_id else None,
        "description": draft.description,
        "generated_name": draft.generated_name,
        "horizon_weeks": draft.horizon_weeks,
        "version": draft.version,
        "expires_at": draft.expires_at,
        **(draft.payload or {}),
    }
