"""Internal endpoint для audio-worker: приём transcript-событий (задел под P1)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.application.use_cases.ingest_transcript_event import IngestTranscriptEvent
from brain_api.container import Container
from brain_api.domain.entities import Meeting
from grey_cardinal_contracts import (
    TranscriptDTO,
    TranscriptEvent,
    TranscriptIngestResponse,
    TranscriptListResponse,
    TranscriptSource,
)

router = APIRouter(
    prefix="/internal/audio",
    tags=["internal-audio"],
    dependencies=[Depends(verify_internal_token)],
)


@router.post("/transcript", response_model=TranscriptIngestResponse)
async def ingest_transcript(
    event: TranscriptEvent,
    container: Container = Depends(get_container),
) -> TranscriptIngestResponse:
    async with container.make_uow() as uow:
        use_case = IngestTranscriptEvent(
            uow,
            container.extractor,
            container.telegram_gateway,
            container.event_publisher,
            container.config,
        )
        return await use_case.execute(event)


@router.get("/transcripts/recent", response_model=TranscriptListResponse)
async def recent_transcripts(
    limit: int = 20,
    container: Container = Depends(get_container),
) -> TranscriptListResponse:
    """Dev endpoint для проверки audio pipeline без доступа audio-worker к БД."""
    async with container.make_uow() as uow:
        events = await uow.transcripts.list_recent(limit)
        meeting_ids = {
            event.meeting_db_id
            for event in events
            if event.meeting_db_id is not None
        }
        meetings = {
            meeting_id: await uow.meetings.get(meeting_id)
            for meeting_id in meeting_ids
        }
    items = [
        TranscriptDTO(
            id=str(event.id),
            meeting_id=event.meeting_id,
            meeting_public_id=_meeting_public_id(event.meeting_db_id, meetings),
            speaker_id=event.speaker_id,
            speaker_name=event.speaker_name,
            text=event.text,
            ts=event.ts,
            is_final=event.is_final,
            confidence=event.confidence,
            source=TranscriptSource(event.source),
            source_payload=(event.raw_json or {}).get("source"),
            speaker=(event.raw_json or {}).get("speaker"),
            raw=event.raw_json or {},
        )
        for event in events
    ]
    return TranscriptListResponse(count=len(items), items=items)


def _meeting_public_id(
    meeting_db_id: UUID | None, meetings: dict[UUID, Meeting | None]
) -> str | None:
    if meeting_db_id is None:
        return None
    meeting = meetings.get(meeting_db_id)
    return meeting.public_id if meeting else None
