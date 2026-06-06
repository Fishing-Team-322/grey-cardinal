"""Per-team board adapter factory for v2 runtime."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain_api.application.ports import BoardGateway
from brain_api.config import Settings
from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskStatus
from brain_api.infrastructure.board.mock import MockBoardGateway
from brain_api.infrastructure.board.yougile import YouGileBoardAdapter
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher
from brain_api.integrations.yougile import YouGileClient


class BoardConfigurationError(RuntimeError):
    pass


@dataclass
class _CacheEntry:
    adapter: BoardGateway
    expires_at: float


class BoardAdapterFactory:
    def __init__(self, session_factory: async_sessionmaker, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._cipher = SecretCipher(settings.board_creds_encryption_key or "dev-key")
        self._cache: dict[UUID, _CacheEntry] = {}

    async def for_team(self, team_id: UUID) -> BoardGateway:
        cached = self._cache.get(team_id)
        now = time.monotonic()
        if cached is not None and cached.expires_at > now:
            return cached.adapter

        async with self._session_factory() as session:
            team = await session.get(m.TeamModel, team_id)
            if team is None:
                raise BoardConfigurationError("Team not found")
            # Disconnected / not-yet-connected teams use the mock board so task
            # creation keeps working locally (see disconnect + auth-error fallback).
            if team.board_provider == "mock" or not team.board_credentials_encrypted:
                adapter: BoardGateway = MockBoardGateway()
            elif team.board_provider == "yougile":
                credentials = json.loads(
                    self._cipher.decrypt_text(team.board_credentials_encrypted) or "{}"
                )
                config = dict(team.board_config or {})
                client = YouGileClient(
                    credentials.get("api_key", ""),
                    base_url=self._settings.yougile_api_base_url,
                    rate_per_minute=self._settings.yougile_rate_limit_per_minute,
                )
                adapter = YouGileBoardAdapter(
                    self._session_factory,
                    team_id,
                    client,
                    config.get("default_column_ids", {}),
                )
            else:
                raise BoardConfigurationError(f"Unsupported board provider: {team.board_provider}")

        self._cache[team_id] = _CacheEntry(adapter=adapter, expires_at=now + 60)
        return adapter

    async def team_id_for_external_card(self, external_card_id: str) -> UUID | None:
        """team_id команды, которой принадлежит карточка доски (по external id)."""
        async with self._session_factory() as session:
            return await session.scalar(
                select(m.BoardCardModel.team_id).where(
                    m.BoardCardModel.external_card_id == external_card_id
                )
            )


class TeamScopedBoardGateway:
    """Board gateway, маршрутизирующий вызовы в адаптер конкретной команды.

    create_card берёт team из самой задачи; move/close/comment — резолвят team по
    BoardCardModel (external_card_id -> team_id). Если команды нет (v1-карточки без
    team_id) — используется fallback-адаптер.
    """

    def __init__(self, factory: BoardAdapterFactory, fallback: BoardGateway) -> None:
        self._factory = factory
        self._fallback = fallback

    async def create_card(self, task: Task):
        if task.team_id is None:
            return await self._fallback.create_card(task)
        adapter = await self._factory.for_team(task.team_id)
        return await adapter.create_card(task)

    async def _adapter_for_card(self, external_card_id: str) -> BoardGateway:
        team_id = await self._factory.team_id_for_external_card(external_card_id)
        if team_id is None:
            return self._fallback
        return await self._factory.for_team(team_id)

    async def move_card(self, external_card_id: str, status: TaskStatus) -> None:
        adapter = await self._adapter_for_card(external_card_id)
        await adapter.move_card(external_card_id, status)

    async def close_card(self, external_card_id: str) -> None:
        adapter = await self._adapter_for_card(external_card_id)
        await adapter.close_card(external_card_id)

    async def add_comment(self, external_card_id: str, text: str) -> None:
        adapter = await self._adapter_for_card(external_card_id)
        await adapter.add_comment(external_card_id, text)
