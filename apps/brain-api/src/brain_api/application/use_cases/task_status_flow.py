"""Кнопки статуса задачи для сотрудника (сценарий 3).

Когда задача «зависла», бот шлёт напоминание с кнопками:
    [🔄 В процессе] [✅ Сделал]
    [🚫 Не буду делать]
Нажатие обновляет статус задачи (и двигает карточку на доске через
UpdateTaskStatus), «Не буду делать» спрашивает причину выбором из пресетов и
переводит задачу в cancelled с записью причины в audit.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from brain_api.application.use_cases.update_task_status import UpdateTaskStatus
from brain_api.domain.entities import AuditLog
from brain_api.domain.enums import TaskStatus
from grey_cardinal_contracts import (
    ActionsResponse,
    AnswerCallbackAction,
    EditMessageAction,
)

CB_TS_PROGRESS = "tsk_prog"
CB_TS_DONE = "tsk_done"
CB_TS_REJECT = "tsk_rej"   # открыть выбор причины
CB_TS_REASON = "tsk_rr"    # tsk_rr:<task_id>:<code>

_PREFIXES = (
    f"{CB_TS_PROGRESS}:",
    f"{CB_TS_DONE}:",
    f"{CB_TS_REJECT}:",
    f"{CB_TS_REASON}:",
)

REASONS = {
    "time": "Нет времени",
    "stale": "Не актуально",
    "reassign": "Передал другому",
    "blocked": "Заблокировано",
    "other": "Другое",
}


def is_task_status_callback(data: str) -> bool:
    return data.startswith(_PREFIXES)


def task_status_keyboard(task_id: UUID) -> dict:
    t = str(task_id)
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 В процессе", "callback_data": f"{CB_TS_PROGRESS}:{t}"},
                {"text": "✅ Сделал", "callback_data": f"{CB_TS_DONE}:{t}"},
            ],
            [{"text": "🚫 Не буду делать", "callback_data": f"{CB_TS_REJECT}:{t}"}],
            [{"text": "🔎 Материалы по задаче", "callback_data": f"help_task:{t}"}],
        ]
    }


def _reason_keyboard(task_id: UUID) -> dict:
    t = str(task_id)
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": f"{CB_TS_REASON}:{t}:{code}"}]
            for code, label in REASONS.items()
        ]
    }


def _ans(cq_id: str, text: str) -> AnswerCallbackAction:
    return AnswerCallbackAction(callback_query_id=cq_id, text=text)


def _edit(event, text: str, kb: dict | None = None) -> EditMessageAction:
    return EditMessageAction(
        chat_id=event.message.chat_id,
        message_id=event.message.message_id,
        text=text,
        reply_markup=kb,
    )


async def handle_task_status_callback(container, data: str, event) -> ActionsResponse:
    cq = event.callback_query_id
    parts = data.split(":")
    action = parts[0]
    try:
        task_id = UUID(parts[1])
    except (IndexError, ValueError):
        return ActionsResponse(actions=[_ans(cq, "Некорректная задача")])

    if action == CB_TS_REJECT:
        return ActionsResponse(actions=[
            _ans(cq, ""),
            _edit(event, "Почему не будешь делать? Выбери причину:", _reason_keyboard(task_id)),
        ])

    if action in (CB_TS_PROGRESS, CB_TS_DONE):
        command = "start_task" if action == CB_TS_PROGRESS else "done"
        async with container.make_uow() as uow:
            result = await UpdateTaskStatus(
                uow, container.board, container.event_publisher, container.config
            ).execute(command, [str(task_id)], event.message.chat_id)
        text = result.actions[0].text if result.actions else "Статус обновлён"
        return ActionsResponse(actions=[_ans(cq, "Готово"), _edit(event, text)])

    if action == CB_TS_REASON:
        code = parts[2] if len(parts) > 2 else "other"
        reason = REASONS.get(code, "Другое")
        async with container.make_uow() as uow:
            task = await uow.tasks.get(task_id)
            if task is None:
                return ActionsResponse(actions=[_ans(cq, "Задача не найдена")])
            task.status = TaskStatus.cancelled
            task.last_status_update_at = container.config.now()
            await uow.tasks.update(task)
            await uow.audit.add(
                AuditLog(
                    id=uuid4(),
                    actor_type="user",
                    actor_id=str(event.from_user.id),
                    action="task_cancelled_by_employee",
                    entity_type="task",
                    entity_id=task.id,
                    payload={"public_id": task.public_id, "reason": reason},
                )
            )
            await uow.commit()
            public_id = task.public_id
        return ActionsResponse(actions=[
            _ans(cq, "Записал причину"),
            _edit(event, f"🚫 {public_id} отменена.\nПричина: {reason}"),
        ])

    return ActionsResponse(actions=[_ans(cq, "Неизвестное действие")])
