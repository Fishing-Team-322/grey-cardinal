from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from brain_api.api.routes.internal_telegram import ingest_callback
from brain_api.api.routes.v2_tenants import team_member_report
from brain_api.application.use_cases.member_reports import (
    manager_report_from_membership,
    manager_report_menu,
    member_report_payload,
    render_member_report,
)
from brain_api.infrastructure.db import models as m
from grey_cardinal_contracts import TelegramCallbackEvent, TelegramMessageRef, TelegramSender

NOW = datetime(2026, 6, 6, 18, 0, tzinfo=UTC)
MANAGER_TG = 7001
EMPLOYEE_TG = 7002


async def _seed(session):
    manager = m.UserModel(display_name="Manager", telegram_user_id=MANAGER_TG)
    employee = m.UserModel(display_name="Employee", telegram_user_id=EMPLOYEE_TG)
    outsider = m.UserModel(display_name="Outsider", telegram_user_id=7003)
    session.add_all([manager, employee, outsider])
    await session.flush()
    company = m.CompanyModel(name="Co", timezone="Europe/Moscow", created_by=manager.id)
    session.add(company)
    await session.flush()
    team = m.TeamModel(company_id=company.id, name="Core", timezone="Europe/Moscow")
    session.add(team)
    await session.flush()
    manager_member = m.TeamMemberModel(team_id=team.id, user_id=manager.id, role="manager")
    employee_member = m.TeamMemberModel(team_id=team.id, user_id=employee.id, role="employee")
    session.add_all([manager_member, employee_member])
    await session.flush()

    project = m.ProjectModel(name="Core project")
    session.add(project)
    await session.flush()
    chat = m.TelegramChatModel(
        team_id=team.id,
        telegram_chat_id=-1007000,
        type="supergroup",
        title="Core",
        project_id=project.id,
    )
    session.add(chat)
    await session.flush()
    message = m.ChatMessageModel(
        telegram_message_id=1,
        chat_id=chat.id,
        sender_id=manager.id,
        text="Employee, закрой задачу",
        raw_json={},
    )
    session.add(message)
    await session.flush()

    done = m.TaskModel(
        seq=1,
        public_id="GC-1",
        team_id=team.id,
        title="Готовая задача",
        status="done",
        priority="medium",
        assignee_id=employee.id,
        source="telegram_chat",
        source_message_id=message.id,
        deadline=NOW - timedelta(hours=1),
        completed_at=NOW - timedelta(hours=2),
        last_status_update_at=NOW - timedelta(hours=2),
        created_at=NOW - timedelta(hours=10),
        updated_at=NOW - timedelta(hours=2),
    )
    overdue = m.TaskModel(
        seq=2,
        public_id="GC-2",
        team_id=team.id,
        title="Просроченная задача",
        status="in_progress",
        priority="high",
        assignee_id=employee.id,
        source="manual",
        deadline=NOW - timedelta(hours=1),
        last_status_update_at=NOW - timedelta(hours=3),
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(hours=3),
    )
    session.add_all([done, overdue])
    await session.flush()
    session.add_all(
        [
            m.BoardCardModel(
                team_id=team.id,
                task_id=done.id,
                provider="yougile",
                external_card_id="card-1",
            ),
            m.UserXpEventModel(
                user_id=employee.id,
                workspace_id=team.id,
                task_id=done.id,
                kind="task_completed",
                points=20,
                reason="Закрыл GC-1",
                metadata_json={"idempotency_key": "task_completed:gc1"},
            ),
        ]
    )
    await session.commit()
    return manager, employee, outsider, team, employee_member


@pytest.mark.asyncio
async def test_member_report_has_delivery_metrics_and_sources(session_factory):
    async with session_factory() as session:
        _, employee, _, team, _ = await _seed(session)
        report = await member_report_payload(session, team_id=team.id, user_id=employee.id, now=NOW)

    assert report is not None
    assert report["metrics"]["assigned_total"] == 2
    assert report["metrics"]["completed_total"] == 1
    assert report["metrics"]["overdue_open"] == 1
    assert report["metrics"]["avg_completion_hours"] == 8.0
    assert report["metrics"]["on_time_rate"] == 100
    assert report["metrics"]["board_synced_tasks"] == 1
    assert report["active_tasks"][0]["public_id"] == "GC-2"
    assert report["recent_completed"][0]["source_author"] == "Manager"
    assert "Среднее время закрытия: 8.0 ч" in render_member_report(report)


@pytest.mark.asyncio
async def test_only_manager_can_open_member_report(session_factory):
    async with session_factory() as session:
        manager, employee, _, team, _ = await _seed(session)
        report = await team_member_report(team.id, employee.id, manager, session)
        with pytest.raises(HTTPException) as exc:
            await team_member_report(team.id, manager.id, employee, session)

    assert report["member"]["display_name"] == "Employee"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_bot_report_menu_and_callback_send_private_report(session_factory):
    async with session_factory() as session:
        _, _, _, _, employee_member = await _seed(session)
        text, keyboard = await manager_report_menu(session, MANAGER_TG)
        report = await manager_report_from_membership(
            session,
            telegram_user_id=MANAGER_TG,
            membership_id=employee_member.id,
        )
    assert "Выберите сотрудника" in text
    callback_data = keyboard["inline_keyboard"][0][0]["callback_data"]
    assert callback_data == f"report:member:{employee_member.id}"
    assert report["member"]["display_name"] == "Employee"

    event = TelegramCallbackEvent(
        update_id=1,
        callback_query_id="cq-report",
        from_user=TelegramSender(id=MANAGER_TG, username="manager", first_name="Manager"),
        message=TelegramMessageRef(message_id=10, chat_id=-1007000),
        data=f"report:member:{employee_member.id}",
    )
    response = await ingest_callback(event, SimpleNamespace(session_factory=session_factory))
    private = [action for action in response.actions if action.type == "send_message"][0]
    assert private.chat_id == MANAGER_TG
    assert "Отчёт: Employee" in private.text
