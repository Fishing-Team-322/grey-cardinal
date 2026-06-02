from datetime import UTC, datetime

from grey_cardinal_contracts import (
    DemoScenarioPayload,
    MeetingStartRequest,
    MeetingStatus,
    MeetingStatusResponse,
    TranscriptEvent,
    TranscriptIngestResponse,
    TranscriptSource,
)


def test_meeting_contracts():
    request = MeetingStartRequest(telegram_chat_id=-100, metadata={"demo": True})
    response = MeetingStatusResponse(
        public_id="MTG-1",
        status=MeetingStatus.active,
        started_at=datetime.now(UTC),
    )

    assert request.metadata["demo"] is True
    assert response.public_id == "MTG-1"


def test_extended_transcript_and_ingest_response():
    event = TranscriptEvent(
        text="Петя, подготовь оплату",
        ts=datetime.now(UTC),
        confidence=0.91,
        source=TranscriptSource.desktop_agent,
    )
    response = TranscriptIngestResponse(
        transcript_id="id",
        meeting_public_id="MTG-1",
        proposal_created=True,
    )

    assert event.source == TranscriptSource.desktop_agent
    assert response.proposal_created is True
    assert DemoScenarioPayload().delay_seconds == 0
