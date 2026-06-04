from sqlalchemy import select

from brain_api.application.use_cases.ingest_transcript_event import IngestTranscriptEvent
from brain_api.application.use_cases.manage_meetings import start_meeting, stop_meeting
from brain_api.domain.enums import MeetingStatus
from brain_api.infrastructure.db import models as m
from conftest import NOW
from grey_cardinal_contracts import TranscriptEvent


async def test_meeting_start_and_stop(make_uow, config):
    async with make_uow() as uow:
        meeting = await start_meeting(
            uow,
            config,
            telegram_chat_id=-100123456789,
            chat_title="Hackathon Team",
        )
        await uow.commit()
        assert meeting.public_id == "MTG-1"
        assert meeting.status == MeetingStatus.active

    async with make_uow() as uow:
        active = await uow.meetings.get_active_for_chat(-100123456789)
        assert active is not None
        stopped = await stop_meeting(uow, config, active)
        await uow.commit()
        assert stopped.status == MeetingStatus.stopped
        assert stopped.stopped_at == NOW.replace(tzinfo=None)


async def test_transcript_attaches_to_active_meeting(
    make_uow, config, extractor, telegram, events, session_factory
):
    async with make_uow() as uow:
        meeting = await start_meeting(
            uow,
            config,
            telegram_chat_id=-100123456789,
        )
        await uow.commit()
        response = await IngestTranscriptEvent(uow, extractor, telegram, events, config).execute(
            TranscriptEvent(
                text="Это промежуточная реплика",
                ts=NOW,
                is_final=False,
            )
        )
    assert response.meeting_public_id == meeting.public_id
    async with session_factory() as session:
        row = await session.scalar(select(m.TranscriptEventModel))
        assert row is not None
        assert row.meeting_db_id == meeting.id
