from sqlalchemy import func, select

from brain_api.application.use_cases.ingest_chat_message import IngestChatMessage
from brain_api.infrastructure.db import models as m


async def _count(session_factory, model) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_task_message_creates_proposal_with_callback_buttons(
    make_uow, extractor, events, config, make_message, session_factory
):
    async with make_uow() as uow:
        response = await IngestChatMessage(uow, extractor, events, config).execute(
            make_message("Петя, подготовь оплату до завтра 18:00")
        )

    assert len(response.actions) == 1
    keyboard = response.actions[0].reply_markup["inline_keyboard"]
    assert keyboard[0][0]["callback_data"].startswith("confirm_task:")
    assert keyboard[0][1]["callback_data"].startswith("reject_task:")
    assert keyboard[1][0]["callback_data"].startswith("edit_task:")
    assert await _count(session_factory, m.TaskProposalModel) == 1
    assert events.events[-1].event.value == "task_proposed"


async def test_small_talk_does_not_create_proposal(
    make_uow, extractor, events, config, make_message, session_factory
):
    async with make_uow() as uow:
        response = await IngestChatMessage(uow, extractor, events, config).execute(
            make_message("Всем привет, как настроение?")
        )
    assert response.actions == []
    assert await _count(session_factory, m.TaskProposalModel) == 0


async def test_repeated_message_is_idempotent(
    make_uow, extractor, events, config, make_message, session_factory
):
    event = make_message("Петя, подготовь оплату до завтра 18:00")
    async with make_uow() as uow:
        await IngestChatMessage(uow, extractor, events, config).execute(event)
    async with make_uow() as uow:
        response = await IngestChatMessage(uow, extractor, events, config).execute(event)
    assert response.actions == []
    assert await _count(session_factory, m.ChatMessageModel) == 1
    assert await _count(session_factory, m.TaskProposalModel) == 1
