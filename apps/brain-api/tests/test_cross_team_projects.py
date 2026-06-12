from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from brain_api.application.project_context import resolve_project_context
from brain_api.application.use_cases.cross_team_projects import (
    build_project_draft,
    create_project_from_draft,
    move_project_task_status,
    project_payload,
)
from brain_api.infrastructure.db import models as m
from brain_api.integrations.yougile import YouGileNotFound


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


class _FakeProjectYouGile:
    """Minimal YouGile client double for project-board task moves."""

    def __init__(self, valid_ids=()):
        self.valid = set(valid_ids)
        self.updates = []
        self.creates = []
        self._n = 0

    async def update_task(self, task_id, **fields):
        self.updates.append((task_id, fields))
        if task_id not in self.valid:
            raise YouGileNotFound("PUT", f"/tasks/{task_id}", 404, '{"message":"not found"}')
        return {"id": task_id, **fields}

    async def create_task(self, title, column_id, **kwargs):
        self._n += 1
        new_id = f"new-card-{self._n}"
        self.valid.add(new_id)
        self.creates.append({"title": title, "column_id": column_id, **kwargs})
        return {"id": new_id}


async def _seed_project_with_task(session, company, team, owner, *, with_card, link_board=True):
    project = m.CompanyProjectModel(
        id=uuid4(),
        company_id=company.id,
        code="PRJ-T",
        name="Test project",
        status="active",
        owner_id=owner.id,
        created_by=owner.id,
        source="manual",
    )
    session.add(project)
    await session.flush()
    task = m.TaskModel(
        id=uuid4(),
        seq=1,
        public_id="GC-1",
        team_id=team.id,
        company_project_id=project.id,
        title="Дизайн и вёрстка",
        status="todo",
        priority="medium",
        source="manual",
    )
    session.add(task)
    if link_board:
        session.add(
            m.ProjectExternalLinkModel(
                id=uuid4(),
                project_id=project.id,
                provider="yougile",
                source_team_id=team.id,
                external_project_id="proj-ext",
                external_board_id="board-ext",
                sync_status="synced",
                payload={
                    "columns": {
                        "todo": "col-todo",
                        "in_progress": "col-prog",
                        "review": "col-rev",
                        "done": "col-done",
                    }
                },
            )
        )
    if with_card:
        session.add(
            m.ExternalTaskLinkModel(
                id=uuid4(),
                team_id=team.id,
                task_id=task.id,
                provider="yougile",
                external_board_id="board-ext",
                external_column_id="col-todo",
                external_task_id="card-1",
                sync_status="synced",
            )
        )
    await session.commit()
    return project, task


async def test_project_task_move_syncs_to_project_board(session_factory):
    async with session_factory() as session:
        director, _, _, company, backend, _ = await _seed_company(session)
        _, task = await _seed_project_with_task(session, company, backend, director, with_card=True)
        fake = _FakeProjectYouGile(valid_ids={"card-1"})
        result = await move_project_task_status(
            session,
            task=task,
            status_value="done",
            settings=None,
            actor_id=director.id,
            client=fake,
        )

    assert result.sync_status == "synced"
    assert result.status == "done"
    assert fake.updates == [("card-1", {"columnId": "col-done", "completed": True})]
    assert fake.creates == []
    async with session_factory() as session:
        stored = await session.get(m.TaskModel, task.id)
        link = await session.scalar(
            select(m.ExternalTaskLinkModel).where(m.ExternalTaskLinkModel.task_id == task.id)
        )
    assert stored.status == "done" and stored.completed_at is not None
    assert link.external_column_id == "col-done" and link.sync_status == "synced"


async def test_project_task_move_recreates_stale_card_on_404(session_factory):
    async with session_factory() as session:
        director, _, _, company, backend, _ = await _seed_company(session)
        _, task = await _seed_project_with_task(session, company, backend, director, with_card=True)
        fake = _FakeProjectYouGile(valid_ids=set())  # card-1 no longer exists -> 404
        result = await move_project_task_status(
            session,
            task=task,
            status_value="in_progress",
            settings=None,
            actor_id=director.id,
            client=fake,
        )

    assert result.sync_status == "synced"
    assert fake.updates[0][0] == "card-1"  # attempted the stale card first
    assert len(fake.creates) == 1
    assert fake.creates[0]["column_id"] == "col-prog"
    async with session_factory() as session:
        link = await session.scalar(
            select(m.ExternalTaskLinkModel).where(m.ExternalTaskLinkModel.task_id == task.id)
        )
    assert link.external_task_id.startswith("new-card-")
    assert link.sync_status == "synced"
    assert link.last_error is None


async def test_project_task_move_local_only_without_project_link(session_factory):
    async with session_factory() as session:
        director, _, _, company, backend, _ = await _seed_company(session)
        _, task = await _seed_project_with_task(
            session, company, backend, director, with_card=False, link_board=False
        )
        fake = _FakeProjectYouGile()
        result = await move_project_task_status(
            session, task=task, status_value="done", settings=None, client=fake
        )

    assert result.sync_status == "local_only"
    assert fake.updates == [] and fake.creates == []
    async with session_factory() as session:
        stored = await session.get(m.TaskModel, task.id)
    assert stored.status == "done"
