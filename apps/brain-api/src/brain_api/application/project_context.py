"""Resolve a company project for Telegram task commands without unsafe guessing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.infrastructure.db import models as m

PROJECT_CODE_RE = re.compile(r"\bPRJ-[A-Z0-9]{4,12}\b", re.IGNORECASE)
TASK_CODE_RE = re.compile(r"\bGC-\d+\b", re.IGNORECASE)


@dataclass(frozen=True)
class ProjectContext:
    project_id: UUID | None
    code: str | None = None
    name: str | None = None
    reason: str = "none"
    ambiguous: bool = False
    candidates: tuple[dict[str, str], ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "project_id": str(self.project_id) if self.project_id else None,
            "code": self.code,
            "name": self.name,
            "reason": self.reason,
            "ambiguous": self.ambiguous,
            "candidates": list(self.candidates),
        }


async def resolve_project_context(
    session: AsyncSession,
    *,
    telegram_chat_id: UUID,
    message_thread_id: int | None,
    team_id: UUID,
    text: str,
) -> ProjectContext:
    binding = await session.scalar(
        select(m.ProjectChatBindingModel)
        .where(
            m.ProjectChatBindingModel.telegram_chat_id == telegram_chat_id,
            m.ProjectChatBindingModel.message_thread_id == message_thread_id,
        )
        .limit(1)
    )
    if binding is None and message_thread_id is not None:
        binding = await session.scalar(
            select(m.ProjectChatBindingModel)
            .where(
                m.ProjectChatBindingModel.telegram_chat_id == telegram_chat_id,
                m.ProjectChatBindingModel.message_thread_id.is_(None),
            )
            .limit(1)
        )
    if binding is not None:
        project = await session.get(m.CompanyProjectModel, binding.project_id)
        if project and project.status in {"active", "paused"}:
            return _resolved(project, "chat_binding")

    task_codes = TASK_CODE_RE.findall(text or "")
    if task_codes:
        shared_task_ids = select(m.TaskTeamModel.task_id).where(
            m.TaskTeamModel.team_id == team_id
        )
        project_ids = list(
            await session.scalars(
                select(m.TaskModel.company_project_id)
                .where(
                func.upper(m.TaskModel.public_id) == task_codes[0].upper(),
                m.TaskModel.company_project_id.is_not(None),
                    or_(
                        m.TaskModel.team_id == team_id,
                        m.TaskModel.id.in_(shared_task_ids),
                    ),
                )
                .distinct()
            )
        )
        referenced = [
            project
            for project_id in project_ids
            if (project := await session.get(m.CompanyProjectModel, project_id)) is not None
        ]
        if len(referenced) == 1:
            return _resolved(referenced[0], "task_reference")
        if len(referenced) > 1:
            return _ambiguous(referenced, "task_reference")

    project_codes = PROJECT_CODE_RE.findall(text or "")
    if project_codes:
        project = await session.scalar(
            select(m.CompanyProjectModel).where(
                func.upper(m.CompanyProjectModel.code) == project_codes[0].upper()
            )
        )
        if project:
            return _resolved(project, "project_code")

    projects = list(
        await session.scalars(
            select(m.CompanyProjectModel)
            .join(m.ProjectTeamModel, m.ProjectTeamModel.project_id == m.CompanyProjectModel.id)
            .where(
                m.ProjectTeamModel.team_id == team_id,
                m.ProjectTeamModel.participation_status == "active",
                m.CompanyProjectModel.status.in_(("active", "paused")),
            )
            .order_by(m.CompanyProjectModel.updated_at.desc())
        )
    )
    normalized = (text or "").casefold()
    named = [
        project
        for project in projects
        if len(project.name.strip()) >= 3 and project.name.casefold() in normalized
    ]
    if len(named) == 1:
        return _resolved(named[0], "project_name")
    if len(named) > 1:
        return _ambiguous(named, "multiple_names")
    if len(projects) == 1:
        return _resolved(projects[0], "single_active_project")
    if len(projects) > 1:
        return _ambiguous(projects, "multiple_active_projects")
    return ProjectContext(project_id=None)


def _resolved(project: m.CompanyProjectModel, reason: str) -> ProjectContext:
    return ProjectContext(
        project_id=project.id,
        code=project.code,
        name=project.name,
        reason=reason,
    )


def _ambiguous(
    projects: list[m.CompanyProjectModel],
    reason: str,
) -> ProjectContext:
    return ProjectContext(
        project_id=None,
        reason=reason,
        ambiguous=True,
        candidates=tuple(
            {"id": str(project.id), "code": project.code, "name": project.name}
            for project in projects[:6]
        ),
    )
