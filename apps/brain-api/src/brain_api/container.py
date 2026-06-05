"""Композиционный корень (DI-контейнер) brain-api.

Собирает singletons (extractor, board, telegram-gateway, event publisher,
session factory) и выдаёт UnitOfWork на каждую операцию.
"""

from __future__ import annotations

import logging
from typing import cast

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from brain_api.application.config import AppConfig
from brain_api.application.ports import (
    BoardGateway,
    EventPublisher,
    TaskExtractor,
    TelegramGateway,
    UnitOfWork,
)
from brain_api.config import Settings
from brain_api.domain.enums import BoardProvider
from brain_api.infrastructure.board.base import YouGileConfig, resolve_provider
from brain_api.infrastructure.board.mock import MockBoardGateway
from brain_api.infrastructure.board.yougile import YouGileBoardGateway
from brain_api.infrastructure.db.repositories import SqlAlchemyUnitOfWork
from brain_api.infrastructure.db.session import create_engine, create_session_factory
from brain_api.infrastructure.events.event_bus import WebSocketEventPublisher
from brain_api.infrastructure.events.websocket_manager import WebSocketManager
from brain_api.infrastructure.llm.client import OpenAICompatibleClient
from brain_api.infrastructure.llm.extractor import LLMTaskExtractor
from brain_api.infrastructure.llm.heuristic_extractor import HeuristicTaskExtractor
from brain_api.infrastructure.telegram_gateway.client import HttpTelegramGateway

logger = logging.getLogger(__name__)


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.config = AppConfig(
            timezone=settings.default_timezone,
            reminder_deadline_hours_before=settings.reminder_deadline_hours_before,
            reminder_stale_hours=settings.reminder_stale_hours,
            evening_digest_hour=settings.evening_digest_hour,
            default_workspace_name=settings.default_workspace_name,
            default_telegram_chat_id=settings.default_telegram_chat_id,
            task_extraction_min_confidence=settings.task_extraction_min_confidence,
            task_extraction_require_action_verb=settings.task_extraction_require_action_verb,
            duplicate_similarity_threshold=settings.duplicate_similarity_threshold,
            reminder_min_interval_minutes=settings.reminder_min_interval_minutes,
            reminder_max_daily_per_user=settings.reminder_max_daily_per_user,
            reminder_quiet_hours_start=settings.reminder_quiet_hours_start,
            reminder_quiet_hours_end=settings.reminder_quiet_hours_end,
            demo_core_auto_confirm=settings.demo_core_auto_confirm,
        )

        self.engine: AsyncEngine = create_engine(settings.database_url, echo=settings.db_echo)
        self.session_factory: async_sessionmaker[AsyncSession] = create_session_factory(self.engine)

        self.websocket_manager = WebSocketManager()
        self.event_publisher: EventPublisher = WebSocketEventPublisher(self.websocket_manager)
        self.telegram_gateway: TelegramGateway = HttpTelegramGateway(
            settings.telegram_bot_base_url, settings.internal_api_token
        )
        self.extractor: TaskExtractor = self._build_extractor(settings)
        self.board: BoardGateway = self._build_board(settings)

    # ------------------------------------------------------------------ #
    def make_uow(self) -> UnitOfWork:
        return cast(UnitOfWork, SqlAlchemyUnitOfWork(self.session_factory()))

    async def dispose(self) -> None:
        await self.engine.dispose()

    # ------------------------------------------------------------------ #
    def _build_extractor(self, settings: Settings) -> TaskExtractor:
        if settings.llm_enabled:
            logger.info("LLM extractor enabled (model=%s)", settings.llm_model)
            client = OpenAICompatibleClient(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
            )
            return LLMTaskExtractor(client)
        logger.info("LLM_API_KEY пуст — используется HeuristicTaskExtractor")
        return HeuristicTaskExtractor()

    def _build_board(self, settings: Settings) -> BoardGateway:
        provider = resolve_provider(settings.board_provider)
        if provider == BoardProvider.yougile:
            cfg = YouGileConfig(
                api_base_url=settings.yougile_api_base_url,
                api_key=settings.yougile_api_key,
                company_id=settings.yougile_company_id or None,
                project_id=settings.yougile_project_id or None,
                board_id=settings.yougile_board_id or None,
                column_backlog_id=settings.yougile_column_backlog_id or None,
                column_todo_id=settings.yougile_column_todo_id or None,
                column_in_progress_id=settings.yougile_column_in_progress_id or None,
                column_review_id=settings.yougile_column_review_id or None,
                column_blocked_id=settings.yougile_column_blocked_id or None,
                column_done_id=settings.yougile_column_done_id or None,
            )
            if cfg.is_configured:
                logger.info("Board provider: YouGile")
                return YouGileBoardGateway(cfg)
            logger.warning(
                "BOARD_PROVIDER=yougile, но не настроен (%s) — откат на MockBoardGateway",
                ", ".join(cfg.missing_required),
            )
        logger.info("Board provider: mock")
        return MockBoardGateway()
