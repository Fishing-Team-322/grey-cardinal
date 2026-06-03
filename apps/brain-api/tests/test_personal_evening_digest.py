"""Тесты персонального вечернего дайджеста (каждому — его задачи)."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from brain_api.application.use_cases.send_personal_evening_digests import (
    SendPersonalEveningDigests,
)
from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskPriority, TaskSource, TaskStatus
from conftest import NOW


async def _user(make_uow, *, tg_id, name="Петя", username="petya"):
    async with make_uow() as uow:
        user = await uow.users.upsert_from_telegram(tg_id, username, name)
        await uow.commit()
    return user


async def _task(
    make_uow,
    seed_chat,
    *,
    user_id=None,
    status=TaskStatus.todo,
    deadline=None,
    completed_at=None,
    public_id="GC-1",
    title="Подготовить оплату",
):
    project, _ = await seed_chat()
    task = Task(
        id=uuid4(),
        public_id=public_id,
        title=title,
        status=status,
        priority=TaskPriority.medium,
        source=TaskSource.telegram_chat,
        project_id=project.id,
        assignee_id=user_id,
        assignee_text="Петя",
        deadline=deadline,
        completed_at=completed_at,
        last_status_update_at=NOW,
    )
    async with make_uow() as uow:
        await uow.tasks.add(task)
        await uow.commit()
    return task


async def test_user_with_tasks_gets_personal_digest(make_uow, seed_chat, telegram, config):
    user = await _user(make_uow, tg_id=555)
    await _task(make_uow, seed_chat, user_id=user.id, deadline=NOW + timedelta(days=1))
    async with make_uow() as uow:
        sent = await SendPersonalEveningDigests(uow, telegram, config).execute()
    assert sent == 1
    chat_id, text = telegram.sent[0]
    assert chat_id == 555
    assert "твои задачи" in text
    assert "GC-1" in text


async def test_user_without_tasks_is_not_spammed(make_uow, seed_chat, telegram, config):
    await _user(make_uow, tg_id=555)  # есть юзер, но нет задач
    await seed_chat()
    async with make_uow() as uow:
        sent = await SendPersonalEveningDigests(uow, telegram, config).execute()
    assert sent == 0
    assert telegram.sent == []


async def test_digest_includes_overdue(make_uow, seed_chat, telegram, config):
    user = await _user(make_uow, tg_id=555)
    await _task(make_uow, seed_chat, user_id=user.id, deadline=NOW - timedelta(hours=1))
    async with make_uow() as uow:
        await SendPersonalEveningDigests(uow, telegram, config).execute()
    text = telegram.sent[0][1]
    assert "Просрочено:" in text


async def test_digest_includes_completed_today(make_uow, seed_chat, telegram, config):
    user = await _user(make_uow, tg_id=555)
    await _task(make_uow, seed_chat, user_id=user.id, deadline=NOW + timedelta(days=1))
    await _task(
        make_uow,
        seed_chat,
        user_id=user.id,
        status=TaskStatus.done,
        completed_at=NOW,
        public_id="GC-2",
        title="Отправить документы",
    )
    async with make_uow() as uow:
        await SendPersonalEveningDigests(uow, telegram, config).execute()
    text = telegram.sent[0][1]
    assert "Закрыто сегодня: 1" in text


async def test_digest_not_sent_twice_per_day(make_uow, seed_chat, telegram, config):
    user = await _user(make_uow, tg_id=555)
    await _task(make_uow, seed_chat, user_id=user.id, deadline=NOW + timedelta(days=1))
    async with make_uow() as uow:
        first = await SendPersonalEveningDigests(uow, telegram, config).execute()
    async with make_uow() as uow:
        second = await SendPersonalEveningDigests(uow, telegram, config).execute()
    assert first == 1
    assert second == 0
    assert len(telegram.sent) == 1


async def test_digest_command_in_private_returns_personal(
    make_uow, seed_chat, telegram, config
):
    user = await _user(make_uow, tg_id=555)
    await _task(make_uow, seed_chat, user_id=user.id, deadline=NOW + timedelta(days=1))
    async with make_uow() as uow:
        actions = await SendPersonalEveningDigests(
            uow, telegram, config
        ).as_actions_for_user(555, 555)
    assert "твои задачи" in actions.actions[0].text
