"""Тесты кнопок статуса задачи (сценарий 3)."""

from __future__ import annotations

import pytest

from brain_api.application.use_cases.task_status_flow import (
    handle_task_status_callback,
    is_task_status_callback,
    task_status_keyboard,
)
from brain_api.domain.enums import TaskStatus
from grey_cardinal_contracts import TelegramCallbackEvent, TelegramMessageRef, TelegramSender


class _Container:
    def __init__(self, make_uow, board, events, config):
        self._make_uow = make_uow
        self.board = board
        self.event_publisher = events
        self.config = config

    def make_uow(self):
        return self._make_uow()


def _cb(data: str) -> TelegramCallbackEvent:
    return TelegramCallbackEvent(
        update_id=1,
        callback_query_id="cq",
        from_user=TelegramSender(id=111, username="petya", first_name="Петя"),
        message=TelegramMessageRef(message_id=900, chat_id=-100123456789),
        data=data,
    )


def test_keyboard_has_three_actions():
    import uuid

    kb = task_status_keyboard(uuid.uuid4())
    cbs = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
    assert any(c.startswith("tsk_prog:") for c in cbs)
    assert any(c.startswith("tsk_done:") for c in cbs)
    assert any(c.startswith("tsk_rej:") for c in cbs)
    assert is_task_status_callback(cbs[0])


@pytest.mark.asyncio
async def test_done_button_closes_task(make_uow, board, events, config, create_confirmed_task):
    task, _ = await create_confirmed_task()
    container = _Container(make_uow, board, events, config)
    data = f"tsk_done:{task.id}"
    resp = await handle_task_status_callback(container, data, _cb(data))
    assert resp.actions[0].type == "answer_callback"
    async with make_uow() as uow:
        refreshed = await uow.tasks.get(task.id)
    assert refreshed.status == TaskStatus.done


@pytest.mark.asyncio
async def test_reject_then_reason_cancels(make_uow, board, events, config, create_confirmed_task):
    task, _ = await create_confirmed_task()
    container = _Container(make_uow, board, events, config)

    # Шаг 1: открыть выбор причины.
    rej = f"tsk_rej:{task.id}"
    opened = await handle_task_status_callback(container, rej, _cb(rej))
    edit = [a for a in opened.actions if a.type == "edit_message"][0]
    reason_cbs = [b["callback_data"] for row in edit.reply_markup["inline_keyboard"] for b in row]
    assert any(c.startswith("tsk_rr:") for c in reason_cbs)

    # Шаг 2: выбрать причину.
    data = f"tsk_rr:{task.id}:time"
    done = await handle_task_status_callback(container, data, _cb(data))
    async with make_uow() as uow:
        refreshed = await uow.tasks.get(task.id)
    assert refreshed.status == TaskStatus.cancelled
    final_edit = [a for a in done.actions if a.type == "edit_message"][0]
    assert "Нет времени" in final_edit.text
