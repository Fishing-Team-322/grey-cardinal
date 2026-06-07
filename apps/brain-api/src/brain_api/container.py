"""Composition root for brain-api."""

from __future__ import annotations

import logging
from typing import cast

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from brain_api.application.board_mirror import BoardMirrorGateway, BoardMirrorService
from brain_api.application.config import AppConfig
from brain_api.application.ports import (
    BoardGateway,
    EventPublisher,
    TaskExtractor,
    TelegramGateway,
    UnitOfWork,
)
from brain_api.application.semantic_parser import SemanticMessageParser
from brain_api.config import Settings
from brain_api.infrastructure.board.factory import BoardAdapterFactory
from brain_api.infrastructure.board.jira import JiraBoardGateway, JiraConfig
from brain_api.infrastructure.board.mock import MockBoardGateway
from brain_api.infrastructure.db.repositories import SqlAlchemyUnitOfWork
from brain_api.infrastructure.db.session import create_engine, create_session_factory
from brain_api.infrastructure.events.event_bus import WebSocketEventPublisher
from brain_api.infrastructure.events.websocket_manager import WebSocketManager
from brain_api.infrastructure.llm.client import OpenAICompatibleClient
from brain_api.infrastructure.llm.extractor import LLMTaskExtractor
from brain_api.infrastructure.llm.heuristic_extractor import HeuristicTaskExtractor
from brain_api.infrastructure.llm.providers import LLMProviderFactory
from brain_api.infrastructure.telegram_gateway.client import HttpTelegramGateway

logger = logging.getLogger(__name__)


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.config = AppConfig(
            timezone=settings.default_timezone,
            reminder_deadline_hours_before=settings.reminder_deadline_hours_before,
            reminder_stale_hours=settings.reminder_stale_hours,
            morning_summary_hour=settings.morning_summary_hour,
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
            settings.telegram_bot_base_url,
            settings.internal_api_token,
        )
        self.llm_provider_factory = LLMProviderFactory(self.session_factory, settings)
        self.semantic_parser = SemanticMessageParser(self.llm_provider_factory)
        self.extractor: TaskExtractor = self._build_extractor(settings)

        self.board_adapter_factory = BoardAdapterFactory(self.session_factory, settings)
        self.board_mirror = BoardMirrorService(self.session_factory, settings)
        self.board: BoardGateway = BoardMirrorGateway(self.board_mirror)

    def make_uow(self) -> UnitOfWork:
        return cast(UnitOfWork, SqlAlchemyUnitOfWork(self.session_factory()))

    async def dispose(self) -> None:
        await self.engine.dispose()

    def _build_extractor(self, settings: Settings) -> TaskExtractor:
        if settings.llm_enabled:
            logger.info("LLM extractor enabled (model=%s)", settings.llm_model)
            client = OpenAICompatibleClient(
                base_url=settings.effective_llm_base_url,
                api_key=settings.effective_llm_api_key,
                model=settings.llm_model,
                timeout=settings.llm_timeout_seconds,
            )
            return LLMTaskExtractor(client)
        if settings.is_production:
            raise RuntimeError("LLM provider must be configured in production")
        logger.info("LLM is not configured; using HeuristicTaskExtractor")
        return HeuristicTaskExtractor()

    def _build_fallback_board(self, settings: Settings) -> BoardGateway:
        """Build only the legacy no-team fallback.

        YouGile is always resolved from TeamModel by BoardAdapterFactory so its
        credentials never come from process environment variables.
        """
        if settings.board_provider == "jira":
            jira_cfg = JiraConfig(
                url=settings.jira_url,
                email=settings.jira_email,
                api_token=settings.jira_api_token,
                project_key=settings.jira_project_key,
                done_transition_id=settings.jira_done_transition_id,
                in_progress_transition_id=settings.jira_in_progress_transition_id,
            )
            if jira_cfg.is_configured:
                logger.info("Fallback board provider: Jira")
                return cast(BoardGateway, JiraBoardGateway(jira_cfg))
            logger.warning("Fallback Jira is incomplete; using mock")
        logger.info("Global board fallback: mock; YouGile is configured per team")
        return MockBoardGateway()
