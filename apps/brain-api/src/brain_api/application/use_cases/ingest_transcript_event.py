"""Use case: приём transcript-события (задел под audio-worker, P1).

На P1: сохраняет событие, публикует websocket transcript_line, и — если из текста
извлекается задача — создаёт proposal так же, как из Telegram-сообщения, и
отправляет его в чат по умолчанию через telegram-bot.
"""

from __future__ import annotations

from uuid import uuid4

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
from grey_cardinal_contracts import (
    EventName,
    KnownUser,
    TranscriptIngestResponse,
    TranscriptSource,
    TranscriptSourceDetails,
    WebsocketEvent,
)
from grey_cardinal_contracts import (
    TranscriptEvent as TranscriptEventContract,
)


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

    async def execute(self, event: TranscriptEventContract) -> TranscriptIngestResponse:
        uow = self._uow
        chat_id = await _default_chat_id(uow, self._config)
        meeting = None
        if event.meeting_id:
            meeting = await uow.meetings.get_by_public_id(event.meeting_id)
        if meeting is None:
            meeting = await uow.meetings.get_active_for_chat(chat_id)

        entity = TranscriptEntity(
            id=uuid4(),
            meeting_id=event.meeting_id,
            meeting_db_id=meeting.id if meeting else None,
            speaker_id=event.speaker_id,
            speaker_name=event.speaker_name,
            text=event.text,
            ts=event.ts,
            is_final=event.is_final,
            confidence=event.confidence,
            source=_source_value(event.source),
            raw_json=event.raw or {},
        )
        await uow.transcripts.add(entity)

        await self._events.publish(
            WebsocketEvent(
                event=EventName.transcript_line,
                payload={
                    "meeting_id": event.meeting_id,
                    "meeting_public_id": meeting.public_id if meeting else None,
                    "speaker_name": event.speaker_name,
                    "text": event.text,
                    "is_final": event.is_final,
                },
            )
        )

        # Извлекаем задачу только из финальных реплик.
        if not event.is_final:
            await uow.commit()
            return TranscriptIngestResponse(
                transcript_id=str(entity.id),
                meeting_public_id=meeting.public_id if meeting else None,
            )

        known_users = [
            KnownUser(display_name=u.display_name, telegram_username=u.telegram_username)
            for u in await uow.users.list_known()
        ]

        # Build conversation context window (last 7 final utterances from same meeting).
        conversation_context: str | None = None
        if entity.meeting_db_id is not None:
            recent = await uow.transcripts.list_recent_for_meeting(
                entity.meeting_db_id, limit=7
            )
            # Filter out the current utterance (already added) and format as dialogue.
            prior = [t for t in recent if t.id != entity.id]
            if prior:
                lines = [
                    f"[{t.speaker_name or t.speaker_id or 'Участник'}]: {t.text}"
                    for t in prior
                ]
                conversation_context = "\n".join(lines)

        extraction = await self._extractor.extract_task(
            text=event.text,
            now=self._config.now(),
            timezone=self._config.timezone,
            known_users=known_users,
            conversation_context=conversation_context,
        )
        if not extraction.has_task:
            await uow.commit()
            return TranscriptIngestResponse(
                transcript_id=str(entity.id),
                meeting_public_id=meeting.public_id if meeting else None,
            )

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
        notified = chat_id is not None
        if chat_id is not None:
            await self._telegram.send_message(chat_id, action.text, action.reply_markup)

        return TranscriptIngestResponse(
            transcript_id=str(entity.id),
            meeting_public_id=meeting.public_id if meeting else None,
            proposal_created=True,
            telegram_notified=notified,
        )


def _source_value(source: TranscriptSource | TranscriptSourceDetails) -> str:
    if isinstance(source, TranscriptSourceDetails):
        return source.kind.value
    return source.value
