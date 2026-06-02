from sqlalchemy import func, select

from brain_api.application.use_cases.confirm_task import ConfirmTask
from brain_api.application.use_cases.ingest_chat_message import IngestChatMessage
from brain_api.infrastructure.db import models as m
from conftest import callback_id_from_actions


async def _count(session_factory, model) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def _proposal_id(make_uow, extractor, events, config, make_message):
    async with make_uow() as uow:
        response = await IngestChatMessage(uow, extractor, events, config).execute(
            make_message("Петя, подготовь оплату до завтра 18:00")
        )
    return callback_id_from_actions(response.actions)


async def test_confirm_creates_task_and_mock_board_card(
    make_uow, extractor, board, events, config, make_message, session_factory
):
    confirmation_id = await _proposal_id(make_uow, extractor, events, config, make_message)
    async with make_uow() as uow:
        response = await ConfirmTask(uow, board, events, config).execute(
            confirmation_id, "cb-1", -100123456789, 102, 111
        )
        task = await uow.tasks.get_by_public_id("GC-1")
        assert task is not None
        card = await uow.board_cards.get_by_task(task.id)

    assert card is not None
    assert card.provider.value == "mock"
    assert [action.type for action in response.actions] == ["answer_callback", "edit_message"]
    assert events.events[-1].event.value == "task_created"


async def test_repeated_confirm_does_not_duplicate_task(
    make_uow, extractor, board, events, config, make_message, session_factory
):
    confirmation_id = await _proposal_id(make_uow, extractor, events, config, make_message)
    for callback_id in ("cb-1", "cb-2"):
        async with make_uow() as uow:
            await ConfirmTask(uow, board, events, config).execute(
                confirmation_id, callback_id, -100123456789, 102, 111
            )
    assert await _count(session_factory, m.TaskModel) == 1
    assert await _count(session_factory, m.BoardCardModel) == 1


async def test_board_error_keeps_local_task(
    make_uow, extractor, events, config, make_message, session_factory
):
    class BrokenBoard:
        async def create_card(self, task):
            raise RuntimeError("board is offline")

    confirmation_id = await _proposal_id(make_uow, extractor, events, config, make_message)
    async with make_uow() as uow:
        response = await ConfirmTask(uow, BrokenBoard(), events, config).execute(
            confirmation_id, "cb-1", -100123456789, 102, 111
        )
    assert await _count(session_factory, m.TaskModel) == 1
    assert await _count(session_factory, m.BoardCardModel) == 0
    assert "сохранена локально" in response.actions[1].text
