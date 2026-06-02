from brain_api.application.use_cases.list_tasks import ListTasks
from brain_api.application.use_cases.update_task_status import UpdateTaskStatus
from brain_api.domain.enums import TaskStatus


async def test_status_commands_update_task_and_board(
    create_confirmed_task, make_uow, board, events, config
):
    task, _ = await create_confirmed_task()
    for command, expected in (
        ("start_task", TaskStatus.in_progress),
        ("block", TaskStatus.blocked),
        ("done", TaskStatus.done),
    ):
        async with make_uow() as uow:
            await UpdateTaskStatus(uow, board, events, config).execute(
                command, [task.public_id], -100123456789
            )
            changed = await uow.tasks.get(task.id)
        assert changed is not None
        assert changed.status == expected
    assert changed.completed_at is not None


async def test_status_command_reports_bad_arguments_and_unknown_task(
    make_uow, board, events, config
):
    async with make_uow() as uow:
        missing = await UpdateTaskStatus(uow, board, events, config).execute(
            "done", [], -100123456789
        )
    async with make_uow() as uow:
        unknown = await UpdateTaskStatus(uow, board, events, config).execute(
            "done", ["GC-999"], -100123456789
        )
    assert "Укажи задачу" in missing.actions[0].text
    assert "не найдена" in unknown.actions[0].text


async def test_tasks_command_is_scoped_to_current_chat(
    create_confirmed_task, make_uow, board, events, config
):
    await create_confirmed_task()
    async with make_uow() as uow:
        visible = await ListTasks(uow, config).execute(-100123456789)
    async with make_uow() as uow:
        hidden = await ListTasks(uow, config).execute(-999)
    assert "GC-1" in visible.actions[0].text
    assert "Активных задач нет" in hidden.actions[0].text
