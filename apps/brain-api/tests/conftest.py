"""Общие фикстуры тестов brain-api.

БД — SQLite in-memory (aiosqlite) с StaticPool, чтобы все сессии видели одну базу.
Внешние зависимости подменены фейками: MockBoardGateway, NullEventPublisher,
NullTelegramGateway, HeuristicTaskExtractor.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from brain_api.application.config import AppConfig
from brain_api.application.use_cases.confirm_task import ConfirmTask
from brain_api.application.use_cases.desktop_client import register_device
from brain_api.application.use_cases.ingest_chat_message import IngestChatMessage
from brain_api.infrastructure.board.mock import MockBoardGateway
from brain_api.infrastructure.db.models import Base
from brain_api.infrastructure.db.repositories import SqlAlchemyUnitOfWork
from brain_api.infrastructure.events.event_bus import NullEventPublisher
from brain_api.infrastructure.llm.heuristic_extractor import HeuristicTaskExtractor
from brain_api.infrastructure.telegram_gateway.client import NullTelegramGateway
from grey_cardinal_contracts import (
    RegisterDeviceRequest,
    TelegramChatInfo,
    TelegramMessageEvent,
    TelegramSender,
)

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


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setattr(AppConfig, "now", lambda self: NOW)


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


@pytest.fixture
def create_confirmed_task(make_uow, extractor, board, events, config, make_message):
    async def _create(
        *, text: str = "Петя, подготовь оплату до завтра 18:00", message_id: int = 100
    ):
        async with make_uow() as uow:
            proposal = await IngestChatMessage(uow, extractor, events, config).execute(
                make_message(text, message_id=message_id)
            )
        confirmation_id = callback_id_from_actions(proposal.actions)
        async with make_uow() as uow:
            response = await ConfirmTask(uow, board, events, config).execute(
                confirmation_id=confirmation_id,
                callback_query_id=f"cb-{message_id}",
                chat_id=-100123456789,
                message_id=message_id + 1,
                actor_telegram_id=111,
            )
            task = await uow.tasks.get_by_public_id("GC-1")
        assert task is not None
        return task, response

    return _create


@pytest.fixture
def seed_chat(make_uow):
    async def _seed(telegram_chat_id: int = -100123456789):
        async with make_uow() as uow:
            project = await uow.projects.ensure_default()
            chat = await uow.chats.upsert(
                telegram_chat_id=telegram_chat_id,
                chat_type="supergroup",
                title=f"Chat {telegram_chat_id}",
                project_id=project.id,
            )
            await uow.commit()
        return project, chat

    return _seed


@pytest.fixture
def register_desktop_identity(make_uow, config):
    async def _register(
        *,
        display_name: str = "Петя",
        telegram_username: str | None = "petya",
        device_name: str = "Petya Laptop",
        platform: str = "windows",
    ):
        async with make_uow() as uow:
            response = await register_device(
                uow,
                config,
                RegisterDeviceRequest(
                    display_name=display_name,
                    telegram_username=telegram_username,
                    device_name=device_name,
                    platform=platform,
                    app_version="0.1.0",
                ),
            )
        return response

    return _register


def desktop_headers(identity) -> dict[str, str]:
    return {
        "X-GC-User-Id": identity.user_id,
        "X-GC-Device-Id": identity.device_id,
        "X-GC-Client-Session-Id": identity.client_session_id,
    }


def callback_id_from_actions(actions) -> UUID:
    """Достать confirmation_id из callback_data кнопки «Создать»."""
    send = actions[0]
    data = send.reply_markup["inline_keyboard"][0][0]["callback_data"]
    return UUID(data.split(":", 1)[1])
