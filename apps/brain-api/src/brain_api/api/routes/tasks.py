"""Internal endpoints для чтения задач (для будущего dashboard/инструментов)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.container import Container
from brain_api.domain.entities import Task
from grey_cardinal_contracts import (
    TaskDTO,
    TaskListResponse,
    TaskPriority,
    TaskSource,
    TaskStatus,
)

router = APIRouter(
    prefix="/internal/tasks",
    tags=["internal-tasks"],
    dependencies=[Depends(verify_internal_token)],
)


async def _to_dto(container: Container, uow, task: Task) -> TaskDTO:
    card = await uow.board_cards.get_by_task(task.id)
    return TaskDTO(
        id=str(task.id),
        public_id=task.public_id,
        title=task.title,
        description=task.description,
        status=TaskStatus(task.status.value),
        priority=TaskPriority(task.priority.value),
        assignee_text=task.assignee_text,
        deadline=task.deadline,
        source=TaskSource(task.source.value),
        board_provider=card.provider.value if card else None,
        board_url=card.external_url if card else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("", response_model=TaskListResponse)
async def list_tasks(container: Container = Depends(get_container)) -> TaskListResponse:
    async with container.make_uow() as uow:
        tasks = await uow.tasks.list_active()
        dtos = [await _to_dto(container, uow, t) for t in tasks]
    return TaskListResponse(tasks=dtos)


@router.get("/{task_id}", response_model=TaskDTO)
async def get_task(task_id: str, container: Container = Depends(get_container)) -> TaskDTO:
    async with container.make_uow() as uow:
        task = None
        try:
            task = await uow.tasks.get(UUID(task_id))
        except ValueError:
            task = await uow.tasks.get_by_public_id(task_id)
        if task is None:
            task = await uow.tasks.get_by_public_id(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return await _to_dto(container, uow, task)
