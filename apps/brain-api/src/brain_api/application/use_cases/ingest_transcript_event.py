"""Use case: приём transcript-события (задел под audio-worker, P1).

На P0: сохраняет событие, публикует websocket transcript_line, и — если из текста
извлекается задача — создаёт proposal так же, как из Telegram-сообщения, и
отправляет его в чат по умолчанию через telegram-bot.
"""

from __future__ import annotations

from uuid import uuid4

from grey_cardinal_contracts import (
    ActionsResponse,
    EventName,
    KnownUser,
    TranscriptEvent as TranscriptEventContract,
    WebsocketEvent,
)

from brain_api.application.config import AppConfig
from brain_api.application.ports import (
    EventPublisher,
    TaskExtractor,
    TelegramGateway,
    UnitOfWork,
)
from brain_api.application.use_cases._shared import create_proposal_with_confirmation
from brain_api.application.use_cases.send_deadline_reminders import _default_chat_id
from brain_api.domain.entities import TranscriptEvent as TranscriptEntity
from brain_api.domain.enums import TaskSource


class IngestTranscriptEvent:
    def __init__(
        self,
        uow: UnitOfWork,
        extractor: TaskExtractor,
        telegram: TelegramGateway,
        events: EventPublisher,
        config: AppConfig,
    ) -> None:
        self._uow = uow
        self._extractor = extractor
        self._telegram = telegram
        self._events = events
        self._config = config

    async def execute(self, event: TranscriptEventContract) -> ActionsResponse:
        uow = self._uow
        entity = TranscriptEntity(
            id=uuid4(),
            meeting_id=event.meeting_id,
            speaker_id=event.speaker_id,
            speaker_name=event.speaker_name,
            text=event.text,
            ts=event.ts,
            is_final=event.is_final,
            raw_json=event.raw or {},
        )
        await uow.transcripts.add(entity)

        await self._events.publish(
            WebsocketEvent(
                event=EventName.transcript_line,
                payload={
                    "meeting_id": event.meeting_id,
                    "speaker_name": event.speaker_name,
                    "text": event.text,
                    "is_final": event.is_final,
                },
            )
        )

        # Извлекаем задачу только из финальных реплик.
        if not event.is_final:
            await uow.commit()
            return ActionsResponse(actions=[])

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

        chat_id = await _default_chat_id(uow)
        action = await create_proposal_with_confirmation(
            uow,
            self._events,
            self._config,
            source=TaskSource.meeting_transcript,
            raw_text=event.text,
            extraction=extraction,
            chat_telegram_id=chat_id,
            source_transcript_id=entity.id,
        )
        await uow.commit()

        # Если есть чат по умолчанию — пушим proposal туда через telegram-bot.
        if chat_id is not None:
            await self._telegram.send_message(chat_id, action.text, action.reply_markup)

        return ActionsResponse(actions=[action])
