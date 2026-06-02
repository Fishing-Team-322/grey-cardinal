"""Use case: приём нормализованного Telegram-сообщения из чата."""

from __future__ import annotations

from uuid import uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import EventPublisher, TaskExtractor, UnitOfWork
from brain_api.application.use_cases._shared import create_proposal_with_confirmation
from brain_api.domain.entities import ChatMessage
from brain_api.domain.enums import TaskSource
from grey_cardinal_contracts import (
    ActionsResponse,
    KnownUser,
    TelegramMessageEvent,
)


class IngestChatMessage:
    def __init__(
        self,
        uow: UnitOfWork,
        extractor: TaskExtractor,
        events: EventPublisher,
        config: AppConfig,
    ) -> None:
        self._uow = uow
        self._extractor = extractor
        self._events = events
        self._config = config

    async def execute(self, event: TelegramMessageEvent) -> ActionsResponse:
        uow = self._uow

        project = await uow.projects.ensure_default(self._config.default_workspace_name)
        chat = await uow.chats.upsert(
            telegram_chat_id=event.chat.id,
            chat_type=event.chat.type,
            title=event.chat.title,
            project_id=project.id,
        )
        sender = await uow.users.upsert_from_telegram(
            telegram_user_id=event.sender.id,
            username=event.sender.username,
            display_name=_display_name(event),
        )

        # Идемпотентность: одно Telegram-сообщение не должно обрабатываться дважды.
        existing = await uow.messages.get_by_tg(chat.id, event.message_id)
        if existing is not None:
            await uow.commit()
            return ActionsResponse(actions=[])

        message = ChatMessage(
            id=uuid4(),
            telegram_message_id=event.message_id,
            chat_id=chat.id,
            sender_id=sender.id,
            text=event.text,
            raw_json=event.raw or {},
        )
        await uow.messages.add(message)

        known_users = [
            KnownUser(display_name=u.display_name, telegram_username=u.telegram_username)
            for u in await uow.users.list_known()
        ]
        extraction = await self._extractor.extract_task(
            text=event.text,
            now=self._config.now(),
            timezone=self._config.timezone,
            known_users=known_users,
        )

        if not extraction.has_task:
            await uow.commit()
            return ActionsResponse(actions=[])

        action = await create_proposal_with_confirmation(
            uow,
            self._events,
            self._config,
            source=TaskSource.telegram_chat,
            raw_text=event.text,
            extraction=extraction,
            chat_telegram_id=event.chat.id,
            source_message_id=message.id,
        )
        await uow.commit()
        return ActionsResponse(actions=[action])


def _display_name(event: TelegramMessageEvent) -> str:
    s = event.sender
    parts = [p for p in (s.first_name, s.last_name) if p]
    if parts:
        return " ".join(parts)
    return s.username or f"user{s.id}"
