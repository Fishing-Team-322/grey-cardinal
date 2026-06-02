from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from brain_api.application.use_cases.confirm_task import ConfirmTask
from brain_api.application.use_cases.desktop_client import (
    desktop_tasks,
    ingest_desktop_transcript,
    resolve_desktop_identity,
)
from brain_api.infrastructure.db import models as m
from conftest import NOW
from grey_cardinal_contracts import DesktopTranscriptRequest


async def test_desktop_tasks_returns_user_tasks(
    register_desktop_identity,
    make_uow,
    extractor,
    telegram,
    events,
    config,
    board,
    session_factory,
):
    registered = await register_desktop_identity()
    async with make_uow() as uow:
        identity = await resolve_desktop_identity(
            uow,
            user_id=UUID(registered.user_id),
            device_id=UUID(registered.device_id),
            client_session_id=UUID(registered.client_session_id),
        )
        await ingest_desktop_transcript(
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

    async with session_factory() as session:
        confirmation = await session.scalar(select(m.ConfirmationModel))
    assert confirmation is not None
    async with make_uow() as uow:
        await ConfirmTask(uow, board, events, config).execute(
            confirmation_id=confirmation.id,
            callback_query_id="cb-1",
            chat_id=-100,
            message_id=10,
        )

    async with make_uow() as uow:
        response = await desktop_tasks(uow, identity)

    assert len(response.tasks) == 1
    assert response.tasks[0].public_id == "GC-1"
    assert response.tasks[0].assignee_text == "Петя"
