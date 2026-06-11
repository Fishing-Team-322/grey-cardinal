"""Cross-team project planning, creation, collaboration events, and YouGile sync."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application.task_numbering import next_task_public_id
from brain_api.application.use_cases.project_simulation import (
    MemberCapacity,
    WorkItem,
    current_capacity,
    decompose_project,
    simulate,
)
from brain_api.config import Settings
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher
from brain_api.integrations.yougile import YouGileClient

PROJECT_DRAFT_TTL = timedelta(days=7)
PROJECT_COLUMNS = (
    ("todo", "К выполнению", 7),
    ("in_progress", "В работе", 3),
    ("review", "На проверке", 6),
    ("done", "Готово", 5),
)


async def build_project_draft(
    session: AsyncSession,
    *,
    company_id: UUID,
    created_by: UUID,
    description: str,
    horizon_weeks: int,
    source_team_id: UUID | None,
    candidate_team_ids: list[UUID] | None,
    provider_factory: object | None,
    now: datetime | None = None,
) -> m.CompanyProjectDraftModel:
    now = now or datetime.now(UTC)
    teams = await _company_teams(session, company_id, candidate_team_ids)
    if not teams:
        raise ValueError("В компании нет доступных команд для проекта")
    source_team_id = source_team_id or teams[0].id
    if source_team_id not in {team.id for team in teams}:
        raise ValueError("Source team must belong to the selected company")

    work_items = await decompose_project(
        description,
        provider_factory=provider_factory,
        team_id=source_team_id,
    )
    if not work_items:
        raise ValueError("Не удалось декомпозировать проект")

    capacities, team_capacities, mood = await _multi_team_capacity(session, teams, now)
    result = simulate(
        work_items,
        capacities,
        mood,
        horizon_weeks=max(1, min(52, horizon_weeks)),
    )
    lead_team_id = _pick_lead_team(teams, team_capacities)
    tasks = _allocate_tasks(
        work_items,
        teams=teams,
        team_capacities=team_capacities,
        lead_team_id=lead_team_id,
        starts_at=now,
        horizon_weeks=max(1, min(52, horizon_weeks)),
    )
    participating_ids = list(dict.fromkeys([str(lead_team_id), *[
        str(task["owner_team_id"]) for task in tasks
    ]]))
    team_payload = []
    for team in teams:
        if str(team.id) not in participating_ids:
            continue
        roles = sorted({
            task["role"] for task in tasks if str(task["owner_team_id"]) == str(team.id)
        })
        team_payload.append(
            {
                "id": str(team.id),
                "name": team.name,
                "role": "lead" if team.id == lead_team_id else "contributor",
                "allocation_percent": _team_allocation(tasks, team.id),
                "matched_roles": roles,
            }
        )

    generated_name = await _generate_project_name(
        description,
        source_team_id=source_team_id,
        provider_factory=provider_factory,
    )
    payload = {
        "name": generated_name,
        "description": description.strip(),
        "expected_result": _expected_result(description),
        "lead_team_id": str(lead_team_id),
        "team_ids": participating_ids,
        "teams": team_payload,
        "tasks": tasks,
        "plan": {
            "can_use_current_team": result.verdict in {"fits", "tight"},
            "recommended": "current",
            "scenarios": {"current": result.to_dict()},
            "skill_matrix": {
                capacity.display_name: capacity.role for capacity in capacities
            },
        },
        "starts_at": now.isoformat(),
        "deadline": (now + timedelta(weeks=max(1, horizon_weeks))).isoformat(),
        "budget_min": result.budget_min,
        "budget_max": result.budget_max,
    }
    draft = m.CompanyProjectDraftModel(
        id=uuid4(),
        company_id=company_id,
        created_by=created_by,
        source_team_id=source_team_id,
        description=description.strip(),
        generated_name=generated_name,
        horizon_weeks=max(1, min(52, horizon_weeks)),
        version=1,
        payload=payload,
        expires_at=now + PROJECT_DRAFT_TTL,
    )
    session.add(draft)
    await session.commit()
    await session.refresh(draft)
    return draft


async def create_project_from_draft(
    session: AsyncSession,
    *,
    draft: m.CompanyProjectDraftModel,
    actor_id: UUID,
    name: str | None = None,
    description: str | None = None,
    expected_result: str | None = None,
    lead_team_id: UUID | None = None,
    team_ids: list[UUID] | None = None,
    starts_at: datetime | None = None,
    deadline: datetime | None = None,
    tasks: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> m.CompanyProjectModel:
    now = now or datetime.now(UTC)
    if _as_utc(draft.expires_at) < now:
        raise ValueError("Черновик проекта устарел, выполните расчёт ещё раз")
    payload = dict(draft.payload or {})
    resolved_team_ids = team_ids or [UUID(value) for value in payload.get("team_ids", [])]
    resolved_lead = lead_team_id or UUID(str(payload["lead_team_id"]))
    if resolved_lead not in resolved_team_ids:
        resolved_team_ids.insert(0, resolved_lead)
    teams = await _company_teams(session, draft.company_id, resolved_team_ids)
    if {team.id for team in teams} != set(resolved_team_ids):
        raise ValueError("Все команды проекта должны принадлежать одной компании")

    task_payloads = tasks or list(payload.get("tasks") or [])
    if not task_payloads:
        raise ValueError("Проект должен содержать хотя бы одну задачу")
    members = await _members_for_teams(session, resolved_team_ids)
    member_ids = {row["user"].id for row in members}
    _validate_project_tasks(task_payloads, set(resolved_team_ids), member_ids)

    project = m.CompanyProjectModel(
        id=uuid4(),
        company_id=draft.company_id,
        code=f"PRJ-{uuid4().hex[:6].upper()}",
        name=(name or payload.get("name") or draft.generated_name).strip()[:160],
        description=(description or payload.get("description") or draft.description).strip(),
        expected_result=(expected_result or payload.get("expected_result") or "").strip() or None,
        status="active",
        owner_id=actor_id,
        created_by=actor_id,
        starts_at=starts_at or _parse_dt(payload.get("starts_at")) or now,
        deadline=deadline or _parse_dt(payload.get("deadline")),
        budget_min=_int_or_none(payload.get("budget_min")),
        budget_max=_int_or_none(payload.get("budget_max")),
        source="planner",
        sync_status="local_only",
        settings={
            "draft_id": str(draft.id),
            "draft_version": draft.version,
            "horizon_weeks": draft.horizon_weeks,
        },
    )
    session.add(project)
    await session.flush()

    for team in teams:
        session.add(
            m.ProjectTeamModel(
                id=uuid4(),
                project_id=project.id,
                team_id=team.id,
                role="lead" if team.id == resolved_lead else "contributor",
                allocation_percent=_payload_team_allocation(payload, team.id),
                participation_status="active",
            )
        )

    seen_members: set[UUID] = set()
    for row in members:
        user = row["user"]
        if user.id in seen_members:
            continue
        seen_members.add(user.id)
        role = "owner" if user.id == actor_id else (
            "manager" if row["membership_role"] == "manager" else "contributor"
        )
        session.add(
            m.ProjectMemberModel(
                id=uuid4(),
                project_id=project.id,
                user_id=user.id,
                team_id=row["team_id"],
                role=role,
                allocation_percent=100,
                active=True,
            )
        )

    created_tasks: list[m.TaskModel] = []
    for item in task_payloads:
        owner_team_id = UUID(str(item["owner_team_id"]))
        task_team_ids = list(dict.fromkeys([
            owner_team_id,
            *[UUID(str(value)) for value in item.get("team_ids") or []],
        ]))
        assignee_ids = [UUID(str(value)) for value in item.get("assignee_ids") or []]
        seq, public_id = await next_task_public_id(session, owner_team_id)
        task = m.TaskModel(
            id=uuid4(),
            seq=seq,
            public_id=public_id,
            company_project_id=project.id,
            team_id=owner_team_id,
            title=str(item["title"]).strip()[:240],
            description=(str(item.get("description") or "").strip() or None),
            status=str(item.get("status") or "todo"),
            priority=str(item.get("priority") or "medium"),
            assignee_id=assignee_ids[0] if assignee_ids else None,
            deadline=_parse_dt(item.get("deadline")),
            source="project_planner",
            source_type="planner",
            source_text=draft.description,
            source_payload={
                "role": item.get("role"),
                "estimated_hours": item.get("estimated_hours"),
                "draft_id": str(draft.id),
            },
        )
        session.add(task)
        await session.flush()
        created_tasks.append(task)
        for team_id in task_team_ids:
            session.add(
                m.TaskTeamModel(
                    id=uuid4(),
                    task_id=task.id,
                    team_id=team_id,
                    role="owner" if team_id == owner_team_id else "contributor",
                )
            )
        for index, user_id in enumerate(assignee_ids):
            session.add(
                m.TaskAssigneeModel(
                    id=uuid4(),
                    task_id=task.id,
                    user_id=user_id,
                    role="owner" if index == 0 else "contributor",
                )
            )

    for team in teams:
        if team.id == resolved_lead:
            continue
        await add_collaboration_event(
            session,
            company_id=project.company_id,
            project_id=project.id,
            kind="project_started",
            source_team_id=resolved_lead,
            target_team_id=team.id,
            actor_user_id=actor_id,
            points=5,
            idempotency_key=f"project_started:{project.id}:{resolved_lead}:{team.id}",
        )
    session.add(
        m.AuditLogModel(
            id=uuid4(),
            actor_type="user",
            actor_id=str(actor_id),
            action="cross_team_project_created",
            entity_type="company_project",
            entity_id=project.id,
            payload={
                "company_id": str(project.company_id),
                "team_ids": [str(value) for value in resolved_team_ids],
                "tasks": len(created_tasks),
                "draft_id": str(draft.id),
            },
        )
    )
    await session.commit()
    await session.refresh(project)
    return project


async def sync_project_to_yougile(
    session: AsyncSession,
    *,
    project_id: UUID,
    source_team_id: UUID,
    settings: Settings,
    client: YouGileClient | None = None,
) -> dict[str, Any]:
    project = await session.get(m.CompanyProjectModel, project_id)
    team = await session.get(m.TeamModel, source_team_id)
    if project is None or team is None:
        raise ValueError("Project or source team not found")
    if team.company_id != project.company_id:
        raise ValueError("YouGile source team must belong to the project company")
    if not team.board_credentials_encrypted:
        project.sync_status = "not_configured"
        project.sync_error = "YouGile не подключён у ведущей команды"
        await session.commit()
        return {"ok": False, "status": project.sync_status, "error": project.sync_error}

    link = await session.scalar(
        select(m.ProjectExternalLinkModel).where(
            m.ProjectExternalLinkModel.project_id == project.id,
            m.ProjectExternalLinkModel.provider == "yougile",
        )
    )
    if link is None:
        link = m.ProjectExternalLinkModel(
            id=uuid4(),
            project_id=project.id,
            provider="yougile",
            source_team_id=source_team_id,
            sync_status="pending",
        )
        session.add(link)
        await session.flush()

    if client is None:
        cipher = SecretCipher(settings.board_creds_encryption_key or "dev-key")
        raw = cipher.decrypt_text(team.board_credentials_encrypted) or "{}"
        api_key = json.loads(raw).get("api_key", "")
        client = YouGileClient(
            api_key,
            base_url=settings.yougile_api_base_url,
            rate_per_minute=settings.yougile_rate_limit_per_minute,
        )

    try:
        members = await _project_members(session, project.id)
        yougile_users = await client.list_users()
        by_email = {
            str(item.get("email") or "").strip().lower(): str(item["id"])
            for item in yougile_users
            if item.get("id")
        }
        local_to_external = {
            row["user"].id: by_email.get(str(row["user"].email or "").lower())
            for row in members
        }
        if not link.external_project_id:
            roles = {
                external_id: (
                    "admin" if row["role"] in {"owner", "manager"} else "worker"
                )
                for row in members
                if (external_id := local_to_external.get(row["user"].id))
            }
            external_project = await client.create_project(project.name, users=roles or None)
            link.external_project_id = str(external_project["id"])
            link.payload = {"project": external_project}

        if not link.external_board_id:
            board = await client.create_board("Проект", link.external_project_id)
            link.external_board_id = str(board["id"])

        column_map = dict((link.payload or {}).get("columns") or {})
        existing_columns = await client.list_columns(board_id=link.external_board_id)
        by_title = {
            str(item.get("title") or "").strip().lower(): str(item["id"])
            for item in existing_columns
            if item.get("id")
        }
        for status, title, color in PROJECT_COLUMNS:
            column_id = column_map.get(status) or by_title.get(title.lower())
            if not column_id:
                column = await client.create_column(title, link.external_board_id, color=color)
                column_id = str(column["id"])
            column_map[status] = column_id

        tasks = list(
            await session.scalars(
                select(m.TaskModel)
                .where(m.TaskModel.company_project_id == project.id)
                .order_by(m.TaskModel.seq)
            )
        )
        created = 0
        updated = 0
        for task in tasks:
            external_link = await session.scalar(
                select(m.ExternalTaskLinkModel).where(
                    m.ExternalTaskLinkModel.task_id == task.id,
                    m.ExternalTaskLinkModel.provider == "yougile",
                )
            )
            assignee_ids = list(
                await session.scalars(
                    select(m.TaskAssigneeModel.user_id).where(
                        m.TaskAssigneeModel.task_id == task.id
                    )
                )
            )
            if task.assignee_id and task.assignee_id not in assignee_ids:
                assignee_ids.insert(0, task.assignee_id)
            assigned = [
                external_id
                for user_id in assignee_ids
                if (external_id := local_to_external.get(user_id))
            ]
            task_fields = {
                "description": _yougile_task_description(session, task, project),
                "assigned": assigned or None,
                "deadline": _yougile_deadline(task.deadline),
            }
            target_column = column_map.get(task.status) or column_map["todo"]
            if external_link is None:
                external = await client.create_task(
                    f"{task.public_id} {task.title}",
                    target_column,
                    **task_fields,
                )
                external_link = m.ExternalTaskLinkModel(
                    id=uuid4(),
                    team_id=task.team_id,
                    task_id=task.id,
                    provider="yougile",
                    external_board_id=link.external_board_id,
                    external_column_id=target_column,
                    external_task_id=str(external["id"]),
                    sync_status="synced",
                    last_synced_at=datetime.now(UTC),
                    raw_payload=external,
                )
                session.add(external_link)
                created += 1
            else:
                await client.update_task(
                    external_link.external_task_id,
                    title=f"{task.public_id} {task.title}",
                    columnId=target_column,
                    description=task_fields["description"],
                    assigned=assigned,
                    deadline=task_fields["deadline"],
                )
                external_link.external_board_id = link.external_board_id
                external_link.external_column_id = target_column
                external_link.sync_status = "synced"
                external_link.last_error = None
                external_link.last_synced_at = datetime.now(UTC)
                updated += 1

        link.payload = {**(link.payload or {}), "columns": column_map}
        link.sync_status = "synced"
        link.last_error = None
        link.last_synced_at = datetime.now(UTC)
        project.sync_status = "synced"
        project.sync_error = None
        await session.commit()
        return {
            "ok": True,
            "status": "synced",
            "external_project_id": link.external_project_id,
            "external_board_id": link.external_board_id,
            "created_tasks": created,
            "updated_tasks": updated,
        }
    except Exception as exc:
        error = _safe_sync_error(exc)
        link.sync_status = "error"
        link.last_error = error
        project.sync_status = "error"
        project.sync_error = error
        await session.commit()
        return {"ok": False, "status": "error", "error": error}


async def add_collaboration_event(
    session: AsyncSession,
    *,
    company_id: UUID,
    kind: str,
    idempotency_key: str,
    project_id: UUID | None = None,
    task_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    source_team_id: UUID | None = None,
    target_team_id: UUID | None = None,
    points: int = 0,
    metadata: dict[str, Any] | None = None,
) -> bool:
    existing = await session.scalar(
        select(m.CollaborationEventModel.id).where(
            m.CollaborationEventModel.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return False
    session.add(
        m.CollaborationEventModel(
            id=uuid4(),
            company_id=company_id,
            project_id=project_id,
            task_id=task_id,
            actor_user_id=actor_user_id,
            source_team_id=source_team_id,
            target_team_id=target_team_id,
            kind=kind,
            points=points,
            idempotency_key=idempotency_key,
            metadata_json=metadata,
        )
    )
    return True


async def record_cross_team_task_completion(
    session: AsyncSession,
    *,
    task: m.TaskModel,
    actor_user_id: UUID | None,
) -> bool:
    if task.company_project_id is None or task.team_id is None:
        return False
    project = await session.get(m.CompanyProjectModel, task.company_project_id)
    if project is None:
        return False
    teams = list(
        await session.scalars(
            select(m.TaskTeamModel.team_id).where(m.TaskTeamModel.task_id == task.id)
        )
    )
    if len(set(teams)) < 2:
        return False
    changed = False
    for team_id in set(teams):
        if team_id == task.team_id:
            continue
        changed = await add_collaboration_event(
            session,
            company_id=project.company_id,
            project_id=project.id,
            task_id=task.id,
            actor_user_id=actor_user_id,
            source_team_id=task.team_id,
            target_team_id=team_id,
            kind="cross_team_task_completed",
            points=15,
            idempotency_key=f"cross_team_task_completed:{task.id}:{team_id}",
        ) or changed
    return changed


async def project_payload(session: AsyncSession, project: m.CompanyProjectModel) -> dict[str, Any]:
    teams = (
        await session.execute(
            select(m.ProjectTeamModel, m.TeamModel)
            .join(m.TeamModel, m.TeamModel.id == m.ProjectTeamModel.team_id)
            .where(m.ProjectTeamModel.project_id == project.id)
            .order_by(m.ProjectTeamModel.role, m.TeamModel.name)
        )
    ).all()
    members = await _project_members(session, project.id)
    tasks = list(
        await session.scalars(
            select(m.TaskModel)
            .where(m.TaskModel.company_project_id == project.id)
            .order_by(m.TaskModel.status, m.TaskModel.deadline, m.TaskModel.seq)
        )
    )
    task_items = []
    for task in tasks:
        task_teams = (
            await session.execute(
                select(m.TaskTeamModel, m.TeamModel)
                .join(m.TeamModel, m.TeamModel.id == m.TaskTeamModel.team_id)
                .where(m.TaskTeamModel.task_id == task.id)
            )
        ).all()
        assignees = (
            await session.execute(
                select(m.TaskAssigneeModel, m.UserModel)
                .join(m.UserModel, m.UserModel.id == m.TaskAssigneeModel.user_id)
                .where(m.TaskAssigneeModel.task_id == task.id)
            )
        ).all()
        task_items.append(
            {
                "id": str(task.id),
                "public_id": task.public_id,
                "title": task.title,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
                "owner_team_id": str(task.team_id),
                "deadline": task.deadline,
                "completed_at": task.completed_at,
                "teams": [
                    {"id": str(team.id), "name": team.name, "role": row.role}
                    for row, team in task_teams
                ],
                "assignees": [
                    {
                        "id": str(user.id),
                        "display_name": user.display_name,
                        "role": row.role,
                        "photo_data_url": user.photo_data_url,
                    }
                    for row, user in assignees
                ],
            }
        )
    return {
        "id": str(project.id),
        "company_id": str(project.company_id),
        "code": project.code,
        "name": project.name,
        "description": project.description,
        "expected_result": project.expected_result,
        "status": project.status,
        "owner_id": str(project.owner_id),
        "starts_at": project.starts_at,
        "deadline": project.deadline,
        "budget_min": project.budget_min,
        "budget_max": project.budget_max,
        "source": project.source,
        "sync_status": project.sync_status,
        "sync_error": project.sync_error,
        "created_at": project.created_at,
        "teams": [
            {
                "id": str(team.id),
                "name": team.name,
                "role": row.role,
                "allocation_percent": row.allocation_percent,
                "participation_status": row.participation_status,
            }
            for row, team in teams
        ],
        "members": [
            {
                "id": str(row["user"].id),
                "display_name": row["user"].display_name,
                "email": row["user"].email,
                "team_id": str(row["team_id"]) if row["team_id"] else None,
                "role": row["role"],
                "photo_data_url": row["user"].photo_data_url,
            }
            for row in members
        ],
        "tasks": task_items,
        "stats": {
            "tasks": len(task_items),
            "done": sum(item["status"] == "done" for item in task_items),
            "blocked": sum(item["status"] == "blocked" for item in task_items),
            "teams": len(teams),
            "members": len(members),
        },
    }


async def _company_teams(
    session: AsyncSession,
    company_id: UUID,
    team_ids: list[UUID] | None,
) -> list[m.TeamModel]:
    statement = select(m.TeamModel).where(m.TeamModel.company_id == company_id)
    if team_ids:
        statement = statement.where(m.TeamModel.id.in_(team_ids))
    return list((await session.execute(statement.order_by(m.TeamModel.name))).scalars().all())


async def _multi_team_capacity(
    session: AsyncSession,
    teams: list[m.TeamModel],
    now: datetime,
) -> tuple[list[MemberCapacity], dict[UUID, list[MemberCapacity]], float]:
    unique: dict[UUID, MemberCapacity] = {}
    by_team: dict[UUID, list[MemberCapacity]] = {}
    moods: list[float] = []
    for team in teams:
        capacities, mood = await current_capacity(session, team.id, now=now)
        by_team[team.id] = capacities
        moods.append(mood)
        for capacity in capacities:
            if capacity.user_id is None:
                continue
            previous = unique.get(capacity.user_id)
            if previous is None or capacity.weekly_capacity_hours > previous.weekly_capacity_hours:
                unique[capacity.user_id] = capacity
    return list(unique.values()), by_team, sum(moods) / len(moods) if moods else 0.7


def _pick_lead_team(
    teams: list[m.TeamModel],
    capacities: dict[UUID, list[MemberCapacity]],
) -> UUID:
    return max(
        teams,
        key=lambda team: (
            sum(cap.weekly_capacity_hours for cap in capacities.get(team.id, [])),
            -len(capacities.get(team.id, [])),
        ),
    ).id


def _allocate_tasks(
    work_items: list[WorkItem],
    *,
    teams: list[m.TeamModel],
    team_capacities: dict[UUID, list[MemberCapacity]],
    lead_team_id: UUID,
    starts_at: datetime,
    horizon_weeks: int,
) -> list[dict[str, Any]]:
    allocated_hours: dict[UUID, float] = {team.id: 0.0 for team in teams}
    tasks: list[dict[str, Any]] = []
    total = max(1, len(work_items))
    for index, item in enumerate(work_items):
        scored = []
        for team in teams:
            caps = team_capacities.get(team.id, [])
            matching = [cap for cap in caps if cap.role == item.role]
            available = sum(cap.weekly_capacity_hours for cap in matching or caps)
            score = (2 if matching else 0, available - allocated_hours[team.id])
            scored.append((score, team))
        owner = max(scored, key=lambda pair: pair[0])[1] if scored else next(
            team for team in teams if team.id == lead_team_id
        )
        allocated_hours[owner.id] += item.hours
        caps = team_capacities.get(owner.id, [])
        candidates = [cap for cap in caps if cap.role == item.role] or caps
        assignee = min(
            candidates,
            key=lambda cap: (cap.active_count, -cap.weekly_capacity_hours),
            default=None,
        )
        deadline = starts_at + timedelta(
            weeks=max(1, round((index + 1) / total * horizon_weeks))
        )
        tasks.append(
            {
                "title": item.title,
                "description": f"Роль: {item.role}. Оценка: {item.hours:g} ч.",
                "role": item.role,
                "estimated_hours": item.hours,
                "owner_team_id": str(owner.id),
                "team_ids": [str(owner.id)],
                "assignee_ids": [str(assignee.user_id)] if assignee and assignee.user_id else [],
                "deadline": deadline.isoformat(),
                "status": "todo",
                "priority": "medium",
            }
        )
    return tasks


async def _members_for_teams(
    session: AsyncSession, team_ids: list[UUID]
) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(m.UserModel, m.TeamMemberModel.team_id, m.TeamMemberModel.role)
        .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
        .where(m.TeamMemberModel.team_id.in_(team_ids))
        .order_by(m.TeamMemberModel.role, m.UserModel.display_name)
    )
    return [
        {"user": user, "team_id": team_id, "membership_role": role}
        for user, team_id, role in rows.all()
    ]


async def _project_members(
    session: AsyncSession, project_id: UUID
) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(m.ProjectMemberModel, m.UserModel)
        .join(m.UserModel, m.UserModel.id == m.ProjectMemberModel.user_id)
        .where(
            m.ProjectMemberModel.project_id == project_id,
            m.ProjectMemberModel.active.is_(True),
        )
        .order_by(m.ProjectMemberModel.role, m.UserModel.display_name)
    )
    return [
        {
            "user": user,
            "team_id": membership.team_id,
            "role": membership.role,
            "allocation_percent": membership.allocation_percent,
        }
        for membership, user in rows.all()
    ]


async def _generate_project_name(
    description: str,
    *,
    source_team_id: UUID,
    provider_factory: object | None,
) -> str:
    if provider_factory is not None:
        try:
            resolved = await provider_factory.resolve_for_team(source_team_id)
            raw = await resolved.primary.complete_json(
                "Придумай короткое деловое название проекта до 6 слов. "
                'Верни строго JSON {"title":"..."}. Описание:\n' + description,
                "project_title",
                json_schema={
                    "name": "project_title",
                    "schema": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}},
                        "required": ["title"],
                    },
                },
            )
            title = str((raw or {}).get("title") or "").strip()
            if title:
                return title[:160]
        except Exception:
            pass
    cleaned = re.sub(r"\s+", " ", description).strip(" .,-")
    first = re.split(r"[.!?\n;]", cleaned, maxsplit=1)[0].strip()
    words = first.split()
    return " ".join(words[:8])[:160] or "Новый проект"


def _expected_result(description: str) -> str:
    cleaned = re.sub(r"\s+", " ", description).strip()
    return f"Реализован и принят результат: {cleaned[:300]}"


def _team_allocation(tasks: list[dict[str, Any]], team_id: UUID) -> int:
    total = sum(float(task.get("estimated_hours") or 0) for task in tasks) or 1
    mine = sum(
        float(task.get("estimated_hours") or 0)
        for task in tasks
        if str(task.get("owner_team_id")) == str(team_id)
    )
    return max(1, min(100, round(mine / total * 100)))


def _payload_team_allocation(payload: dict[str, Any], team_id: UUID) -> int:
    for team in payload.get("teams") or []:
        if str(team.get("id")) == str(team_id):
            return max(1, min(100, int(team.get("allocation_percent") or 100)))
    return 100


def _validate_project_tasks(
    tasks: list[dict[str, Any]],
    team_ids: set[UUID],
    member_ids: set[UUID],
) -> None:
    for index, item in enumerate(tasks):
        if not str(item.get("title") or "").strip():
            raise ValueError(f"У задачи {index + 1} нет названия")
        owner_team_id = UUID(str(item.get("owner_team_id")))
        if owner_team_id not in team_ids:
            raise ValueError("Ответственная команда задачи не входит в проект")
        for value in item.get("team_ids") or []:
            if UUID(str(value)) not in team_ids:
                raise ValueError("Участвующая команда задачи не входит в проект")
        for value in item.get("assignee_ids") or []:
            if UUID(str(value)) not in member_ids:
                raise ValueError("Исполнитель не входит в выбранные команды проекта")


def _yougile_task_description(
    session: AsyncSession,
    task: m.TaskModel,
    project: m.CompanyProjectModel,
) -> str:
    del session
    lines = [
        f"Проект Grey Cardinal: {project.code} · {project.name}",
        f"Ответственная команда: {task.team_id}",
    ]
    if task.description:
        lines.extend(["", task.description])
    lines.extend(["", f"Grey Cardinal task: {task.public_id}"])
    return "\n".join(lines)


def _yougile_deadline(value: datetime | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"deadline": int(_as_utc(value).timestamp() * 1000), "withTime": True}


def _safe_sync_error(exc: Exception) -> str:
    text = re.sub(r"(?i)(token|key|password)[=:]\s*\S+", r"\1=<redacted>", str(exc))
    return text[:500] or exc.__class__.__name__


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _int_or_none(value: Any) -> int | None:
    return int(value) if value not in (None, "") else None

