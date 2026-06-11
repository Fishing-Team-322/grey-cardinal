from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from brain_api.application.project_context import resolve_project_context
from brain_api.application.use_cases.cross_team_projects import (
    build_project_draft,
    create_project_from_draft,
    project_payload,
)
from brain_api.infrastructure.db import models as m


async def _seed_company(session):
    director = m.UserModel(id=uuid4(), display_name="Director", email="director@example.com")
    backend_user = m.UserModel(
        id=uuid4(),
        display_name="Backend",
        email="backend@example.com",
        bio="backend developer API",
    )
    frontend_user = m.UserModel(
        id=uuid4(),
        display_name="Frontend",
        email="frontend@example.com",
        bio="frontend designer interface",
    )
    company = m.CompanyModel(
        id=uuid4(),
        name="Acme",
        timezone="Europe/Moscow",
        created_by=director.id,
    )
    backend = m.TeamModel(
        id=uuid4(),
        company_id=company.id,
        name="Backend",
        timezone="Europe/Moscow",
        board_provider="yougile",
    )
    frontend = m.TeamModel(
        id=uuid4(),
        company_id=company.id,
        name="Frontend",
        timezone="Europe/Moscow",
        board_provider="yougile",
    )
    session.add_all([director, backend_user, frontend_user, company, backend, frontend])
    await session.flush()
    session.add_all(
        [
            m.CompanyAdminModel(
                id=uuid4(),
                company_id=company.id,
                user_id=director.id,
                role="director",
            ),
            m.TeamMemberModel(
                id=uuid4(),
                team_id=backend.id,
                user_id=director.id,
                role="manager",
            ),
            m.TeamMemberModel(
                id=uuid4(),
                team_id=backend.id,
                user_id=backend_user.id,
                role="employee",
            ),
            m.TeamMemberModel(
                id=uuid4(),
                team_id=frontend.id,
                user_id=frontend_user.id,
                role="employee",
            ),
        ]
    )
    await session.commit()
    return director, backend_user, frontend_user, company, backend, frontend


async def test_draft_creates_shared_project_tasks_atomically(session_factory):
    async with session_factory() as session:
        director, backend_user, frontend_user, company, backend, frontend = (
            await _seed_company(session)
        )
        draft = await build_project_draft(
            session,
            company_id=company.id,
            created_by=director.id,
            description="Создать API интеграции, интерфейс руководителя и отчётность",
            horizon_weeks=6,
            source_team_id=backend.id,
            candidate_team_ids=[backend.id, frontend.id],
            provider_factory=None,
            now=datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
        )
        project = await create_project_from_draft(
            session,
            draft=draft,
            actor_id=director.id,
            lead_team_id=backend.id,
            team_ids=[backend.id, frontend.id],
            tasks=[
                {
                    "title": "Собрать общий API-контракт",
                    "description": "Совместная задача двух команд",
                    "owner_team_id": str(backend.id),
                    "team_ids": [str(backend.id), str(frontend.id)],
                    "assignee_ids": [str(backend_user.id), str(frontend_user.id)],
                    "deadline": "2026-06-25T12:00:00+00:00",
                    "status": "todo",
                    "priority": "high",
                }
            ],
            now=datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
        )

        task = await session.scalar(
            select(m.TaskModel).where(m.TaskModel.company_project_id == project.id)
        )
        assert task is not None
        assert task.team_id == backend.id
        assert await session.scalar(
            select(func.count()).select_from(m.TaskTeamModel).where(
                m.TaskTeamModel.task_id == task.id
            )
        ) == 2
        assert await session.scalar(
            select(func.count()).select_from(m.TaskAssigneeModel).where(
                m.TaskAssigneeModel.task_id == task.id
            )
        ) == 2
        assert await session.scalar(
            select(func.count()).select_from(m.CollaborationEventModel).where(
                m.CollaborationEventModel.project_id == project.id,
                m.CollaborationEventModel.kind == "project_started",
            )
        ) == 1

        payload = await project_payload(session, project)
        assert payload["stats"] == {
            "tasks": 1,
            "done": 0,
            "blocked": 0,
            "teams": 2,
            "members": 3,
        }
        assert len(payload["tasks"][0]["teams"]) == 2
        assert len(payload["tasks"][0]["assignees"]) == 2


async def test_project_context_requires_explicit_choice_when_chat_has_many_projects(
    session_factory,
):
    async with session_factory() as session:
        director, _, _, company, backend, frontend = await _seed_company(session)
        chat = m.TelegramChatModel(
            id=uuid4(),
            team_id=backend.id,
            telegram_chat_id=-100123,
            type="supergroup",
            title="Backend",
        )
        projects = [
            m.CompanyProjectModel(
                id=uuid4(),
                company_id=company.id,
                code=code,
                name=name,
                status="active",
                owner_id=director.id,
                created_by=director.id,
                source="manual",
            )
            for code, name in (("PRJ-ALPHA", "Alpha"), ("PRJ-BETA", "Beta"))
        ]
        session.add_all([chat, *projects])
        await session.flush()
        for project in projects:
            session.add(
                m.ProjectTeamModel(
                    id=uuid4(),
                    project_id=project.id,
                    team_id=backend.id,
                    role="lead",
                    participation_status="active",
                )
            )
        await session.commit()

        ambiguous = await resolve_project_context(
            session,
            telegram_chat_id=chat.id,
            message_thread_id=None,
            team_id=backend.id,
            text="Создай задачу на завтра",
        )
        assert ambiguous.ambiguous is True
        assert len(ambiguous.candidates) == 2

        explicit = await resolve_project_context(
            session,
            telegram_chat_id=chat.id,
            message_thread_id=None,
            team_id=backend.id,
            text="Для PRJ-BETA создай задачу на завтра",
        )
        assert explicit.project_id == projects[1].id
        assert explicit.reason == "project_code"

        session.add(
            m.ProjectChatBindingModel(
                id=uuid4(),
                project_id=projects[0].id,
                telegram_chat_id=chat.id,
                message_thread_id=42,
                kind="project",
                created_by=director.id,
            )
        )
        await session.commit()
        bound = await resolve_project_context(
            session,
            telegram_chat_id=chat.id,
            message_thread_id=42,
            team_id=backend.id,
            text="Создай задачу",
        )
        assert bound.project_id == projects[0].id
        assert bound.reason == "chat_binding"
