"""Team-scoped task public id allocation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.infrastructure.db import models as m


async def next_task_sequence(session: AsyncSession, team_id: UUID | None) -> int:
    statement = select(func.max(m.TaskModel.seq))
    if team_id is not None:
        statement = statement.where(m.TaskModel.team_id == team_id)
    current = await session.scalar(statement)
    return int(current or 0) + 1


async def next_task_public_id(session: AsyncSession, team_id: UUID | None) -> tuple[int, str]:
    seq = await next_task_sequence(session, team_id)
    return seq, f"GC-{seq}"
