from datetime import timedelta

from sqlalchemy import func, select

from brain_api.application.use_cases.ingest_transcript_event import IngestTranscriptEvent
from brain_api.infrastructure.db import models as m
from conftest import NOW
from grey_cardinal_contracts import TranscriptEvent


async def _count(session_factory, model) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


def _event(*, is_final: bool = True) -> TranscriptEvent:
    return TranscriptEvent(
        meeting_id="demo",
        speaker_name="Петя",
        text="Аня, проверь интеграцию до завтра",
        ts=NOW + timedelta(minutes=1),
        is_final=is_final,
    )


async def test_non_final_transcript_is_saved_without_proposal(
    make_uow, extractor, telegram, events, config, session_factory
):
    async with make_uow() as uow:
        response = await IngestTranscriptEvent(uow, extractor, telegram, events, config).execute(
            _event(is_final=False)
        )
    assert response.proposal_created is False
    assert response.telegram_notified is False
    assert await _count(session_factory, m.TranscriptEventModel) == 1
    assert await _count(session_factory, m.TaskProposalModel) == 0
    assert events.events[-1].event.value == "transcript_line"


async def test_final_transcript_creates_proposal_and_pushes_to_default_chat(
    make_uow, extractor, telegram, events, config, session_factory, seed_chat
):
    await seed_chat()
    async with make_uow() as uow:
        response = await IngestTranscriptEvent(uow, extractor, telegram, events, config).execute(
            _event()
        )
    assert response.proposal_created is True
    assert response.telegram_notified is True
    assert telegram.sent[-1][0] == -100123456789
    assert await _count(session_factory, m.TaskProposalModel) == 1


async def test_final_transcript_without_default_chat_has_no_telegram_action(
    make_uow, extractor, telegram, events, config, session_factory
):
    async with make_uow() as uow:
        response = await IngestTranscriptEvent(uow, extractor, telegram, events, config).execute(
            _event()
        )
    assert response.proposal_created is True
    assert response.telegram_notified is False
    assert await _count(session_factory, m.TaskProposalModel) == 1
