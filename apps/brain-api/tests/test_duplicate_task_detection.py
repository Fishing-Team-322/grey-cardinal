"""Тесты детекции дублей (FindSimilarTask + интеграция в IngestChatMessage)."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from brain_api.application.use_cases.find_similar_task import (
    FindSimilarTask,
    score_similarity,
)
from brain_api.application.use_cases.ingest_chat_message import IngestChatMessage
from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskPriority, TaskSource, TaskStatus
from brain_api.infrastructure.db import models as m
from conftest import NOW
from sqlalchemy import func, select

THURSDAY = NOW.replace(day=4, hour=18, minute=0)


async def _seed_task(
    make_uow,
    seed_chat,
    *,
    title="Подготовить оплату",
    status=TaskStatus.todo,
    assignee_text="Петя",
    assignee_id=None,
    deadline=THURSDAY,
):
    project, _ = await seed_chat()
    task = Task(
        id=uuid4(),
        public_id="GC-1",
        title=title,
        status=status,
        priority=TaskPriority.medium,
        source=TaskSource.telegram_chat,
        project_id=project.id,
        assignee_text=assignee_text,
        assignee_id=assignee_id,
        deadline=deadline,
        last_status_update_at=NOW,
    )
    async with make_uow() as uow:
        await uow.tasks.add(task)
        await uow.commit()
    return project, task


async def _count(session_factory, model) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_similar_active_task_is_detected(make_uow, seed_chat, config):
    project, task = await _seed_task(make_uow, seed_chat)
    async with make_uow() as uow:
        result = await FindSimilarTask(uow, config).execute(
            title="надо сделать оплату к четвергу",
            assignee_id=None,
            assignee_text=None,
            deadline=THURSDAY,
            project_id=project.id,
        )
    assert result.is_duplicate is True
    assert result.task is not None
    assert result.task.public_id == "GC-1"
    assert result.score >= config.duplicate_similarity_threshold


async def test_done_task_does_not_block_new_task(make_uow, seed_chat, config):
    project, _ = await _seed_task(make_uow, seed_chat, status=TaskStatus.done)
    async with make_uow() as uow:
        result = await FindSimilarTask(uow, config).execute(
            title="надо сделать оплату к четвергу",
            assignee_id=None,
            assignee_text=None,
            deadline=THURSDAY,
            project_id=project.id,
        )
    assert result.is_duplicate is False


async def test_different_assignee_lowers_score(seed_chat, make_uow):
    project, task = await _seed_task(make_uow, seed_chat, assignee_text="Петя")
    same = score_similarity(
        title="надо сделать оплату к четвергу",
        assignee_id=None,
        assignee_text="Петя",
        deadline=THURSDAY,
        project_id=project.id,
        task=task,
    )
    different = score_similarity(
        title="надо сделать оплату к четвергу",
        assignee_id=None,
        assignee_text="Вася",
        deadline=THURSDAY,
        project_id=project.id,
        task=task,
    )
    assert different < same


async def test_duplicate_message_does_not_create_second_proposal(
    create_confirmed_task, make_uow, extractor, events, config, make_message, session_factory
):
    # GC-1 уже создана и подтверждена (дедлайн завтра 18:00).
    await create_confirmed_task(
        text="Петя, подготовь оплату до завтра 18:00", message_id=100
    )
    proposals_before = await _count(session_factory, m.TaskProposalModel)

    async with make_uow() as uow:
        response = await IngestChatMessage(uow, extractor, events, config).execute(
            make_message("надо сделать оплату завтра", message_id=200, username=None,
                         first_name="Аня", user_id=222)
        )

    # Дубль -> proposal не создаётся, в чат уходит предупреждение.
    assert await _count(session_factory, m.TaskProposalModel) == proposals_before
    assert len(response.actions) == 1
    assert "такая задача уже есть" in response.actions[0].text
    assert any(e.event.value == "duplicate_task_detected" for e in events.events)


async def test_duplicate_warning_includes_existing_public_id(
    create_confirmed_task, make_uow, extractor, events, config, make_message
):
    await create_confirmed_task(
        text="Петя, подготовь оплату до завтра 18:00", message_id=100
    )
    async with make_uow() as uow:
        response = await IngestChatMessage(uow, extractor, events, config).execute(
            make_message("надо сделать оплату завтра", message_id=201, username=None,
                         first_name="Аня", user_id=222)
        )
    text = response.actions[0].text
    assert "GC-1" in text
    assert "Не создаю дубль" in text


async def test_deadline_proximity_within_72h_still_counts(make_uow, seed_chat, config):
    project, _ = await _seed_task(make_uow, seed_chat, deadline=THURSDAY)
    async with make_uow() as uow:
        result = await FindSimilarTask(uow, config).execute(
            title="подготовить оплату",
            assignee_id=None,
            assignee_text="Петя",
            deadline=THURSDAY + timedelta(hours=2),
            project_id=project.id,
        )
    assert result.is_duplicate is True
