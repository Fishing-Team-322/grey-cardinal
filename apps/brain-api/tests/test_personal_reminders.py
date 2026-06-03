"""Тесты адресной доставки напоминаний (личка/чат) и анти-спам подавления."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from brain_api.application.config import AppConfig
from brain_api.application.use_cases.send_deadline_reminders import SendDeadlineReminders
from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskPriority, TaskSource, TaskStatus
from brain_api.infrastructure.db import models as m
from conftest import NOW

CHAT_ID = -100123456789
TG_USER_ID = 555


async def _user_with_tg(make_uow, *, tg_id=TG_USER_ID, name="Петя", username="petya"):
    async with make_uow() as uow:
        user = await uow.users.upsert_from_telegram(tg_id, username, name)
        await uow.commit()
    return user


async def _assigned_task(
    make_uow,
    seed_chat,
    *,
    assignee_id=None,
    assignee_text="Петя",
    deadline,
):
    project, _ = await seed_chat()
    task = Task(
        id=uuid4(),
        public_id="GC-1",
        title="Подготовить оплату",
        status=TaskStatus.todo,
        priority=TaskPriority.medium,
        source=TaskSource.telegram_chat,
        project_id=project.id,
        assignee_id=assignee_id,
        assignee_text=assignee_text,
        deadline=deadline,
        last_status_update_at=NOW,
    )
    async with make_uow() as uow:
        await uow.tasks.add(task)
        await uow.commit()
    return project, task


async def _seed_reminder_logs(session_factory, task_id, *, recipient, count, base, kind="stale"):
    async with session_factory() as s:
        for i in range(count):
            s.add(
                m.ReminderLogModel(
                    id=uuid4(),
                    task_id=task_id,
                    kind=kind,
                    recipient_telegram_user_id=recipient,
                    telegram_chat_id=recipient,
                    sent_at=base - timedelta(minutes=i),
                    payload={},
                )
            )
        await s.commit()


def _suppressed(events, reason):
    return any(
        e.event.value == "reminder_suppressed" and e.payload.get("reason") == reason
        for e in events.events
    )


async def test_reminder_goes_to_assignee_private(make_uow, seed_chat, telegram, events, config):
    user = await _user_with_tg(make_uow)
    await _assigned_task(
        make_uow, seed_chat, assignee_id=user.id, deadline=NOW + timedelta(hours=1)
    )
    async with make_uow() as uow:
        sent = await SendDeadlineReminders(uow, telegram, events, config).execute()
    assert sent == 1
    assert telegram.sent[0][0] == TG_USER_ID  # ушло в личку


async def test_reminder_fallback_to_chat_when_assignee_unknown(
    make_uow, seed_chat, telegram, events, config
):
    await _assigned_task(
        make_uow, seed_chat, assignee_id=None, deadline=NOW + timedelta(hours=1)
    )
    async with make_uow() as uow:
        sent = await SendDeadlineReminders(uow, telegram, events, config).execute()
    assert sent == 1
    assert telegram.sent[0][0] == CHAT_ID  # рабочий чат


async def test_quiet_hours_suppresses(make_uow, seed_chat, telegram, events):
    user = await _user_with_tg(make_uow)
    await _assigned_task(
        make_uow, seed_chat, assignee_id=user.id, deadline=NOW + timedelta(hours=1)
    )
    config = AppConfig(
        reminder_deadline_hours_before=2,
        reminder_quiet_hours_start="00:00",
        reminder_quiet_hours_end="23:00",
    )
    async with make_uow() as uow:
        sent = await SendDeadlineReminders(uow, telegram, events, config).execute()
    assert sent == 0
    assert telegram.sent == []
    assert _suppressed(events, "quiet_hours")


async def test_max_daily_suppresses(
    make_uow, seed_chat, telegram, events, config, session_factory
):
    user = await _user_with_tg(make_uow)
    _, task = await _assigned_task(
        make_uow, seed_chat, assignee_id=user.id, deadline=NOW + timedelta(hours=1)
    )
    await _seed_reminder_logs(
        session_factory, task.id, recipient=TG_USER_ID, count=3, base=NOW - timedelta(minutes=10)
    )
    async with make_uow() as uow:
        sent = await SendDeadlineReminders(uow, telegram, events, config).execute()
    assert sent == 0
    assert _suppressed(events, "max_daily")


async def test_min_interval_suppresses(make_uow, seed_chat, telegram, events, session_factory):
    user = await _user_with_tg(make_uow)
    _, task = await _assigned_task(
        make_uow, seed_chat, assignee_id=user.id, deadline=NOW + timedelta(hours=1)
    )
    await _seed_reminder_logs(
        session_factory, task.id, recipient=TG_USER_ID, count=1, base=NOW - timedelta(minutes=30)
    )
    config = AppConfig(
        reminder_deadline_hours_before=2,
        reminder_min_interval_minutes=120,
        reminder_max_daily_per_user=10,
    )
    async with make_uow() as uow:
        sent = await SendDeadlineReminders(uow, telegram, events, config).execute()
    assert sent == 0
    assert _suppressed(events, "min_interval")


async def test_deadline_reminder_not_duplicated(make_uow, seed_chat, telegram, events, config):
    user = await _user_with_tg(make_uow)
    await _assigned_task(
        make_uow, seed_chat, assignee_id=user.id, deadline=NOW + timedelta(hours=1)
    )
    for expected in (1, 0):
        async with make_uow() as uow:
            sent = await SendDeadlineReminders(uow, telegram, events, config).execute()
        assert sent == expected
    assert len(telegram.sent) == 1
