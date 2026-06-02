"""Общие фикстуры тестов brain-api.

БД — SQLite in-memory (aiosqlite) с StaticPool, чтобы все сессии видели одну базу.
Внешние зависимости подменены фейками: MockBoardGateway, NullEventPublisher,
NullTelegramGateway, HeuristicTaskExtractor.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from grey_cardinal_contracts import (
    TelegramChatInfo,
    TelegramMessageEvent,
    TelegramSender,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from brain_api.application.config import AppConfig
from brain_api.infrastructure.board.mock import MockBoardGateway
from brain_api.infrastructure.db.models import Base
from brain_api.infrastructure.db.repositories import SqlAlchemyUnitOfWork
from brain_api.infrastructure.events.event_bus import NullEventPublisher
from brain_api.infrastructure.llm.heuristic_extractor import HeuristicTaskExtractor
from brain_api.infrastructure.telegram_gateway.client import NullTelegramGateway

TZ = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 6, 2, 15, 0, tzinfo=TZ)  # вторник


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest.fixture
def make_uow(session_factory):
    def _make() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory())

    return _make


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        timezone="Europe/Moscow",
        reminder_deadline_hours_before=2,
        reminder_stale_hours=24,
        evening_digest_hour=20,
    )


@pytest.fixture
def board() -> MockBoardGateway:
    return MockBoardGateway()


@pytest.fixture
def events() -> NullEventPublisher:
    return NullEventPublisher()


@pytest.fixture
def telegram() -> NullTelegramGateway:
    return NullTelegramGateway()


@pytest.fixture
def extractor() -> HeuristicTaskExtractor:
    return HeuristicTaskExtractor()


@pytest.fixture
def make_message():
    def _make(
        text: str,
        *,
        message_id: int = 100,
        chat_id: int = -100123456789,
        user_id: int = 111,
        username: str | None = "petya",
        first_name: str | None = "Петя",
    ) -> TelegramMessageEvent:
        return TelegramMessageEvent(
            update_id=message_id,
            message_id=message_id,
            chat=TelegramChatInfo(id=chat_id, type="supergroup", title="Hackathon Team"),
            sender=TelegramSender(id=user_id, username=username, first_name=first_name),
            text=text,
            date=NOW,
        )

    return _make


def callback_id_from_actions(actions) -> str:
    """Достать confirmation_id из callback_data кнопки «Создать»."""
    send = actions[0]
    data = send.reply_markup["inline_keyboard"][0][0]["callback_data"]
    return data.split(":", 1)[1]
