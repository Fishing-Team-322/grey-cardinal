"""Single status-change entrypoint for local tasks and mirrored YouGile cards."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from brain_api.application.board_mirror import BoardMirrorService
from brain_api.domain.enums import TaskStatus
from brain_api.infrastructure.db import models as m


@dataclass(frozen=True)
class TaskStatusUpdateResult:
    task_id: UUID
    public_id: str
    status: str
    sync_status: str
    sync_error: str | None


class TaskStatusService:
    def __init__(self, mirror: BoardMirrorService) -> None:
        self._mirror = mirror

    async def update_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        *,
        actor_id: UUID | str | int | None = None,
        reason: str | None = None,
        action: str = "task_status_changed",
    ) -> TaskStatusUpdateResult:
        sync = (
            await self._mirror.close_task(task_id)
            if status == TaskStatus.done
            else await self._mirror.move_task(task_id, status)
        )
        async with self._mirror.session_factory()() as session:
            task = await session.get(m.TaskModel, task_id)
            if task is None:
                return TaskStatusUpdateResult(
                    task_id=task_id,
                    public_id="",
                    status=status.value,
                    sync_status=sync.sync_status,
                    sync_error=sync.error,
                )
            session.add(
                m.AuditLogModel(
                    id=uuid4(),
                    actor_type="user" if actor_id else "system",
                    actor_id=str(actor_id) if actor_id else None,
                    action=action,
                    entity_type="task",
                    entity_id=task.id,
                    payload={
                        "public_id": task.public_id,
                        "status": status.value,
                        "reason": reason,
                        "sync_status": sync.sync_status,
                        "sync_error": sync.error,
                    },
                )
            )
            await session.commit()
            return TaskStatusUpdateResult(
                task_id=task.id,
                public_id=task.public_id,
                status=task.status,
                sync_status=sync.sync_status,
                sync_error=sync.error,
            )
