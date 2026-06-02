"""Internal endpoint для audio-worker: приём transcript-событий (задел под P1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from grey_cardinal_contracts import ActionsResponse, TranscriptEvent

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.application.use_cases.ingest_transcript_event import IngestTranscriptEvent
from brain_api.container import Container

router = APIRouter(
    prefix="/internal/audio",
    tags=["internal-audio"],
    dependencies=[Depends(verify_internal_token)],
)


@router.post("/transcript", response_model=ActionsResponse)
async def ingest_transcript(
    event: TranscriptEvent,
    container: Container = Depends(get_container),
) -> ActionsResponse:
    async with container.make_uow() as uow:
        use_case = IngestTranscriptEvent(
            uow,
            container.extractor,
            container.telegram_gateway,
            container.event_publisher,
            container.config,
        )
        return await use_case.execute(event)
