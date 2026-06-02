from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from brain_api.application.use_cases.desktop_client import (
    ingest_desktop_transcript,
    resolve_desktop_identity,
)
from brain_api.infrastructure.db import models as m
from conftest import NOW
from grey_cardinal_contracts import DesktopTranscriptRequest


async def test_desktop_transcript_is_saved_with_trusted_speaker(
    register_desktop_identity, make_uow, extractor, telegram, events, config, session_factory
):
    registered = await register_desktop_identity()
    async with make_uow() as uow:
        identity = await resolve_desktop_identity(
            uow,
            user_id=UUID(registered.user_id),
            device_id=UUID(registered.device_id),
            client_session_id=UUID(registered.client_session_id),
        )
        response = await ingest_desktop_transcript(
            uow,
            extractor,
            telegram,
            events,
            config,
            identity,
            DesktopTranscriptRequest(
                meeting_id="MTG-1",
                text="Это финальная реплика без задачи",
                ts=NOW,
            ),
        )

    assert response.trusted_speaker is True
    async with session_factory() as session:
        row = await session.scalar(select(m.TranscriptEventModel))

    assert row is not None
    assert row.source == "desktop_app"
    assert row.speaker_id == registered.user_id
    assert row.raw_json["speaker"]["identity_source"] == "authenticated_client"
    assert row.raw_json["speaker"]["identity_confidence"] == 1.0
    assert row.raw_json["source"]["capture_mode"] == "microphone"
