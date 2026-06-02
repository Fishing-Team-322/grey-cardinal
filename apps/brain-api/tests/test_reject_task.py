from sqlalchemy import func, select

from brain_api.application.use_cases.confirm_task import ConfirmTask
from brain_api.application.use_cases.ingest_chat_message import IngestChatMessage
from brain_api.application.use_cases.reject_task import RejectTask
from brain_api.infrastructure.db import models as m
from conftest import callback_id_from_actions


async def test_reject_prevents_later_confirmation(
    make_uow, extractor, board, events, config, make_message, session_factory
):
    async with make_uow() as uow:
        proposal = await IngestChatMessage(uow, extractor, events, config).execute(
            make_message("Петя, подготовь оплату до завтра 18:00")
        )
    confirmation_id = callback_id_from_actions(proposal.actions)

    async with make_uow() as uow:
        rejected = await RejectTask(uow, events).execute(
            confirmation_id, "cb-reject", -100123456789, 102, 111
        )
    async with make_uow() as uow:
        confirmed = await ConfirmTask(uow, board, events, config).execute(
            confirmation_id, "cb-confirm", -100123456789, 102, 111
        )
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(m.TaskModel))

    assert [action.type for action in rejected.actions] == ["answer_callback", "edit_message"]
    assert len(confirmed.actions) == 1
    assert confirmed.actions[0].type == "answer_callback"
    assert count == 0
    assert any(event.event.value == "task_rejected" for event in events.events)
