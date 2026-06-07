"""Repository over yougile_mappings + yougile_sync_log.

Idempotent upsert keyed by UNIQUE(team_id, entity_type, yougile_id) so discovery
can run any number of times. Portable (select-then-write) to work on both
Postgres (prod) and SQLite (tests).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.infrastructure.db import models as m

EntityType = str  # 'project' | 'board' | 'column' | 'task' | 'user'


class YouGileMappingRepo:
    def __init__(self, session: AsyncSession, team_id: UUID) -> None:
        self._session = session
        self._team_id = team_id
        self._last_log_at: datetime | None = None

    async def upsert(
        self,
        entity_type: EntityType,
        yougile_id: str,
        *,
        local_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> m.YouGileMappingModel:
        existing = await self.find_by_yougile(entity_type, yougile_id)
        now = datetime.now(UTC)
        if existing is not None:
            existing.last_synced_at = now
            if payload is not None:
                existing.payload = payload
            if local_id is not None:
                existing.local_id = local_id
            return existing
        row = m.YouGileMappingModel(
            team_id=self._team_id,
            entity_type=entity_type,
            yougile_id=yougile_id,
            local_id=local_id,
            payload=payload,
            last_synced_at=now,
        )
        self._session.add(row)
        return row

    async def find_by_yougile(
        self, entity_type: EntityType, yougile_id: str
    ) -> m.YouGileMappingModel | None:
        return await self._session.scalar(
            select(m.YouGileMappingModel).where(
                m.YouGileMappingModel.team_id == self._team_id,
                m.YouGileMappingModel.entity_type == entity_type,
                m.YouGileMappingModel.yougile_id == yougile_id,
            )
        )

    async def find_by_local(
        self, entity_type: EntityType, local_id: UUID
    ) -> m.YouGileMappingModel | None:
        return await self._session.scalar(
            select(m.YouGileMappingModel).where(
                m.YouGileMappingModel.team_id == self._team_id,
                m.YouGileMappingModel.entity_type == entity_type,
                m.YouGileMappingModel.local_id == local_id,
            )
        )

    async def yougile_id_for_local(self, entity_type: EntityType, local_id: UUID) -> str | None:
        row = await self.find_by_local(entity_type, local_id)
        return row.yougile_id if row else None

    async def list_by_type(self, entity_type: EntityType) -> list[m.YouGileMappingModel]:
        rows = await self._session.execute(
            select(m.YouGileMappingModel).where(
                m.YouGileMappingModel.team_id == self._team_id,
                m.YouGileMappingModel.entity_type == entity_type,
            )
        )
        return list(rows.scalars().all())

    async def count_by_type(self, entity_type: EntityType) -> int:
        rows = await self.list_by_type(entity_type)
        return len(rows)

    def log(
        self,
        *,
        direction: str,
        event: str,
        entity_type: str | None = None,
        yougile_id: str | None = None,
        local_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        created_at = datetime.now(UTC)
        if self._last_log_at is not None and created_at <= self._last_log_at:
            created_at = self._last_log_at + timedelta(microseconds=1)
        self._last_log_at = created_at
        self._session.add(
            m.YouGileSyncLogModel(
                team_id=self._team_id,
                direction=direction,
                event=event,
                entity_type=entity_type,
                yougile_id=yougile_id,
                local_id=local_id,
                payload=payload,
                error=error,
                created_at=created_at,
            )
        )

    async def prune_logs(self, keep: int = 10_000) -> None:
        stale_ids = (
            select(m.YouGileSyncLogModel.id)
            .where(m.YouGileSyncLogModel.team_id == self._team_id)
            .order_by(
                m.YouGileSyncLogModel.created_at.desc(),
                m.YouGileSyncLogModel.id.desc(),
            )
            .offset(keep)
        )
        await self._session.execute(
            delete(m.YouGileSyncLogModel).where(m.YouGileSyncLogModel.id.in_(stale_ids))
        )
