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


async def _identity(make_uow, registered):
    async with make_uow() as uow:
        return await resolve_desktop_identity(
            uow,
            user_id=UUID(registered.user_id),
            device_id=UUID(registered.device_id),
            client_session_id=UUID(registered.client_session_id),
        )


async def test_self_assignment_from_authenticated_speaker(
    register_desktop_identity, make_uow, extractor, telegram, events, config, session_factory
):
    registered = await register_desktop_identity(display_name="Петя", telegram_username="petya")
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
                text="Я подготовлю оплату до завтра 18:00",
                ts=NOW,
            ),
        )

    assert response.proposal_created is True
    async with session_factory() as session:
        proposal = await session.scalar(select(m.TaskProposalModel))

    assert proposal is not None
    assert proposal.assignee_text == "Петя"
    assert proposal.assignee_id == UUID(registered.user_id)
    assert proposal.title == "Подготовить оплату"


async def test_explicit_assignment_to_mentioned_user(
    register_desktop_identity, make_uow, extractor, telegram, events, config, session_factory
):
    petya = await register_desktop_identity(display_name="Петя", telegram_username="petya")
    anya = await register_desktop_identity(
        display_name="Аня",
        telegram_username="anya",
        device_name="Anya Laptop",
    )
    identity = await _identity(make_uow, petya)

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
                text="Аня, проверь интеграцию с YouGile сегодня вечером",
                ts=NOW,
            ),
        )

    assert response.proposal_created is True
    async with session_factory() as session:
        proposal = await session.scalar(select(m.TaskProposalModel))

    assert proposal is not None
    assert proposal.assignee_text == "Аня"
    assert proposal.assignee_id == UUID(anya.user_id)
