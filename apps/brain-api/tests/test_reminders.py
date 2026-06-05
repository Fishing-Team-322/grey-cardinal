from datetime import timedelta
from uuid import uuid4

from brain_api.application.use_cases.send_deadline_reminders import SendDeadlineReminders
from brain_api.application.use_cases.send_evening_digest import SendEveningDigest
from brain_api.application.use_cases.send_morning_task_summary import SendMorningTaskSummary
from brain_api.application.use_cases.send_stale_status_reminders import SendStaleStatusReminders
from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskPriority, TaskSource, TaskStatus
from conftest import NOW


async def _seed_task(make_uow, seed_chat, *, deadline=None, last_status_update_at=None):
    project, _ = await seed_chat()
    task = Task(
        id=uuid4(),
        public_id="GC-1",
        title="Проверить оплату",
        status=TaskStatus.todo,
        priority=TaskPriority.medium,
        source=TaskSource.manual,
        project_id=project.id,
        deadline=deadline,
        last_status_update_at=last_status_update_at,
    )
    async with make_uow() as uow:
        await uow.tasks.add(task)
        await uow.commit()
    return task


async def test_deadline_reminder_is_sent_once(make_uow, telegram, events, config, seed_chat):
    await _seed_task(make_uow, seed_chat, deadline=NOW + timedelta(hours=1))
    for expected in (1, 0):
        async with make_uow() as uow:
            sent = await SendDeadlineReminders(uow, telegram, events, config).execute()
        assert sent == expected
    assert len(telegram.sent) == 1


async def test_stale_reminder_is_sent_once_within_cooldown(
    make_uow, telegram, events, config, seed_chat
):
    await _seed_task(make_uow, seed_chat, last_status_update_at=NOW - timedelta(hours=25))
    for expected in (1, 0):
        async with make_uow() as uow:
            sent = await SendStaleStatusReminders(uow, telegram, events, config).execute()
        assert sent == expected
    assert len(telegram.sent) == 1


async def test_digest_action_and_scheduler_send_are_generated_once(
    make_uow, telegram, config, seed_chat
):
    await _seed_task(make_uow, seed_chat)
    async with make_uow() as uow:
        actions = await SendEveningDigest(uow, telegram, config).as_actions(-100123456789)
    assert "Вечерний дайджест" in actions.actions[0].text
    async with make_uow() as uow:
        sent = await SendEveningDigest(uow, telegram, config).execute()
    assert sent == 0


async def test_morning_summary_lists_active_tasks_and_tags_deadline_owner(
    make_uow, telegram, config, seed_chat
):
    project, _ = await seed_chat()
    async with make_uow() as uow:
        user = await uow.users.upsert_from_telegram(111, "petya", "Петя")
        await uow.tasks.add(
            Task(
                id=uuid4(),
                public_id="GC-1",
                title="Проверить оплату",
                status=TaskStatus.todo,
                priority=TaskPriority.medium,
                source=TaskSource.manual,
                project_id=project.id,
                assignee_id=user.id,
                assignee_text="Петя",
                deadline=NOW + timedelta(hours=1),
                last_status_update_at=NOW,
            )
        )
        await uow.commit()

    async with make_uow() as uow:
        sent = await SendMorningTaskSummary(uow, telegram, config).execute()

    assert sent == 1
    assert len(telegram.sent) == 1
    text = telegram.sent[0][1]
    assert "Утренняя сверка задач" in text
    assert "@petya" in text
    assert "Скоро дедлайн" in text
