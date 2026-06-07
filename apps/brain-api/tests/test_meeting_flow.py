"""Тесты флоу созвонов (сценарий 2): предложение → подтверждение → RSVP → пинг."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from brain_api.application.use_cases.meeting_flow import (
    build_meeting_proposal,
    handle_meeting_callback,
    handle_pending_meeting_time,
)
from brain_api.application.use_cases.meeting_reminders import (
    run_meeting_finalize,
    run_meeting_reminders,
)
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.telegram_gateway.client import NullTelegramGateway
from grey_cardinal_contracts import TelegramCallbackEvent, TelegramMessageRef, TelegramSender

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
MANAGER_TG = 5001
EMP_TG = 5002
GROUP_CHAT = -100999


async def _seed(session, *, scheduled_at):
    company = m.CompanyModel(name="Co", timezone="Europe/Moscow", created_by=uuid4())
    session.add(company)
    await session.flush()
    manager = m.UserModel(
        telegram_user_id=MANAGER_TG, telegram_username="boss", display_name="Boss"
    )
    employee = m.UserModel(telegram_user_id=EMP_TG, telegram_username="emp", display_name="Emp")
    session.add_all([manager, employee])
    await session.flush()
    team = m.TeamModel(
        company_id=company.id, name="Team A", timezone="Europe/Moscow", tg_chat_id=GROUP_CHAT
    )
    session.add(team)
    await session.flush()
    session.add_all([
        m.TeamMemberModel(team_id=team.id, user_id=manager.id, role="manager"),
        m.TeamMemberModel(team_id=team.id, user_id=employee.id, role="employee"),
    ])
    meeting = m.MeetingModel(
        seq=1,
        public_id="MTG-1",
        team_id=team.id,
        title="Созвон",
        status="proposed",
        state="proposed",
        created_by=manager.id,
        scheduled_at=scheduled_at,
        scheduled_timezone="Europe/Moscow",
        duration_minutes=60,
        started_at=scheduled_at or NOW,
    )
    session.add(meeting)
    await session.flush()
    return team, manager, employee, meeting


def _cb(data: str, *, from_id: int, chat_id: int, msg_id: int = 700) -> TelegramCallbackEvent:
    return TelegramCallbackEvent(
        update_id=1,
        callback_query_id="cq1",
        from_user=TelegramSender(id=from_id, username="u", first_name="U"),
        message=TelegramMessageRef(message_id=msg_id, chat_id=chat_id),
        data=data,
    )


@pytest.mark.asyncio
async def test_proposal_dms_manager_with_confirm_buttons(session_factory):
    async with session_factory() as session:
        team, manager, _emp, meeting = await _seed(session, scheduled_at=NOW + timedelta(hours=2))
        resp = await build_meeting_proposal(session, team, manager, meeting, GROUP_CHAT)
    action = resp.actions[0]
    assert action.chat_id == MANAGER_TG  # личка руководителю
    cbs = [b["callback_data"] for row in action.reply_markup["inline_keyboard"] for b in row]
    assert any(c.startswith("mtg_ok:") for c in cbs)


@pytest.mark.asyncio
async def test_confirm_posts_poll_to_group(session_factory):
    async with session_factory() as session:
        team, manager, _emp, meeting = await _seed(session, scheduled_at=NOW + timedelta(hours=2))
        await session.commit()
        event = _cb(f"mtg_ok:{meeting.id}", from_id=MANAGER_TG, chat_id=MANAGER_TG)
        resp = await handle_meeting_callback(session, event.data, event)
        refreshed = await session.get(m.MeetingModel, meeting.id)
        assert refreshed.state == "scheduled"
    poll = [a for a in resp.actions if getattr(a, "chat_id", None) == GROUP_CHAT]
    assert poll, "опрос должен уйти в чат команды"
    cbs = [b["callback_data"] for row in poll[0].reply_markup["inline_keyboard"] for b in row]
    assert any(c.startswith("rsvp_yes:") for c in cbs)


@pytest.mark.asyncio
async def test_rsvp_yes_updates_tally(session_factory):
    async with session_factory() as session:
        team, _mgr, emp, meeting = await _seed(session, scheduled_at=NOW + timedelta(hours=2))
        meeting.state = "scheduled"
        await session.commit()
        event = _cb(f"rsvp_yes:{meeting.id}", from_id=EMP_TG, chat_id=GROUP_CHAT)
        resp = await handle_meeting_callback(session, event.data, event)
        rsvp = await session.scalar(select_rsvp(meeting.id, emp.id))
        assert rsvp.status == "yes"
    edit = [a for a in resp.actions if a.type == "edit_message"][0]
    assert "Придут: 1" in edit.text


@pytest.mark.asyncio
async def test_5min_reminder_pings_attendees(session_factory):
    async with session_factory() as session:
        team, _mgr, emp, meeting = await _seed(session, scheduled_at=NOW + timedelta(minutes=4))
        meeting.state = "scheduled"
        session.add(m.MeetingRsvpModel(meeting_id=meeting.id, user_id=emp.id, status="yes"))
        await session.commit()

    gateway = NullTelegramGateway()
    sent = await run_meeting_reminders(session_factory, gateway, now=NOW)
    assert sent == 1
    assert gateway.sent[0][0] == EMP_TG
    # повторный прогон не дублирует
    sent2 = await run_meeting_reminders(session_factory, gateway, now=NOW)
    assert sent2 == 0


@pytest.mark.asyncio
async def test_pending_time_then_confirm(session_factory):
    async with session_factory() as session:
        team, manager, _emp, meeting = await _seed(session, scheduled_at=None)
        meeting.metadata_json = {"awaiting_time_from": MANAGER_TG}
        await session.commit()
        sender = TelegramSender(id=MANAGER_TG, username="boss", first_name="Boss")
        resp = await handle_pending_meeting_time(session, sender, "давайте в 18:30", NOW)
        refreshed = await session.get(m.MeetingModel, meeting.id)
        assert refreshed.scheduled_at is not None
    assert resp is not None
    action = resp.actions[0]
    cbs = [b["callback_data"] for row in action.reply_markup["inline_keyboard"] for b in row]
    assert any(c.startswith("mtg_ok:") for c in cbs)


@pytest.mark.asyncio
async def test_finalize_stores_ai_summary_and_awards_xp(session_factory):
    class Provider:
        async def complete_json(self, prompt, schema_name):
            assert schema_name == "meeting_summary"
            assert "обсудили релиз" in prompt
            return {
                "summary": "Команда согласовала план релиза.",
                "highlights": ["Релиз в пятницу"],
                "decisions": ["Заморозить scope"],
                "next_steps": ["Проверить сборку"],
                "risks": ["Мало времени на QA"],
            }

    class Factory:
        async def for_team(self, team_id):
            return Provider()

    scheduled_at = NOW - timedelta(hours=2)
    async with session_factory() as session:
        team, manager, _emp, meeting = await _seed(session, scheduled_at=scheduled_at)
        meeting.state = "scheduled"
        meeting.status = "scheduled"
        session.add(
            m.TranscriptEventModel(
                meeting_db_id=meeting.id,
                meeting_id=meeting.public_id,
                speaker_name="Boss",
                text="обсудили релиз",
                ts=scheduled_at + timedelta(minutes=10),
                is_final=True,
                source="audio_worker",
            )
        )
        await session.commit()

    gateway = NullTelegramGateway()
    finalized = await run_meeting_finalize(
        session_factory,
        gateway,
        now=NOW,
        llm_provider_factory=Factory(),
    )

    async with session_factory() as session:
        refreshed = await session.get(m.MeetingModel, meeting.id)
        xp = await session.scalar(
            select_xp(manager.id, "meeting_summary_ready")
        )

    assert finalized == 1
    assert refreshed.summary.startswith("AI-саммари")
    assert "Заморозить scope" in refreshed.summary
    assert xp is not None
    assert "Команда согласовала план релиза" in gateway.sent[0][1]


def select_rsvp(meeting_id, user_id):
    from sqlalchemy import select

    return select(m.MeetingRsvpModel).where(
        m.MeetingRsvpModel.meeting_id == meeting_id,
        m.MeetingRsvpModel.user_id == user_id,
    )


def select_xp(user_id, kind):
    from sqlalchemy import select

    return select(m.UserXpEventModel).where(
        m.UserXpEventModel.user_id == user_id,
        m.UserXpEventModel.kind == kind,
    )
