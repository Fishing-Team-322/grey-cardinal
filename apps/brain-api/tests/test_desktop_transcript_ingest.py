from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select

from brain_api.application.use_cases.desktop_client import (
    ingest_desktop_transcript,
    resolve_desktop_identity,
)
from brain_api.infrastructure.db import models as m
from conftest import NOW
from grey_cardinal_contracts import CaptureMode, DesktopTranscriptRequest


async def _identity(make_uow, registered):
    async with make_uow() as uow:
        return await resolve_desktop_identity(
            uow,
            user_id=UUID(registered.user_id),
            device_id=UUID(registered.device_id),
            client_session_id=UUID(registered.client_session_id),
        )


async def test_non_final_desktop_transcript_does_not_create_proposal(
    register_desktop_identity, make_uow, extractor, telegram, events, config, session_factory
):
    registered = await register_desktop_identity()
    identity = await _identity(make_uow, registered)

    async with make_uow() as uow:
        response = await ingest_desktop_transcript(
            uow,
            extractor,
            telegram,
            events,
            config,
            identity,
            DesktopTranscriptRequest(
                meeting_id="MTG-1",
                text="Промежуточная реплика",
                ts=NOW,
                is_final=False,
            ),
        )

    assert response.proposal_created is False
    async with session_factory() as session:
        proposal_count = await session.scalar(select(func.count()).select_from(m.TaskProposalModel))
    assert proposal_count == 0


async def test_desktop_transcript_rejects_non_microphone_capture(
    register_desktop_identity, make_uow, extractor, telegram, events, config
):
    registered = await register_desktop_identity()
    identity = await _identity(make_uow, registered)

    async with make_uow() as uow:
        try:
            await ingest_desktop_transcript(
                uow,
                extractor,
                telegram,
                events,
                config,
                identity,
                DesktopTranscriptRequest(
                    meeting_id="MTG-1",
                    text="loopback is not trusted identity",
                    capture_mode=CaptureMode.system_loopback_experimental,
                ),
            )
        except ValueError as exc:
            assert "microphone" in str(exc)
        else:
            raise AssertionError("expected non-microphone transcript to be rejected")
