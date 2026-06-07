"""Item 4: /api/daemon/state — agent-token auth + tenant-scoping + время встречи."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from brain_api.api.routes.daemon import DaemonAuthError, resolve_daemon_state
from brain_api.infrastructure.db import models as m

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
SETTINGS = SimpleNamespace(meeting_arm_minutes_before=5, meeting_default_duration_minutes=60)


async def _seed(session, *, member=True):
    company = m.CompanyModel(name="Co", timezone="Europe/Moscow", created_by=uuid4())
    session.add(company)
    await session.flush()
    user = m.UserModel(display_name="Agent User")
    session.add(user)
    await session.flush()
    team = m.TeamModel(company_id=company.id, name="Team A", timezone="Europe/Moscow")
    other = m.TeamModel(company_id=company.id, name="Team B", timezone="Europe/Moscow")
    session.add_all([team, other])
    await session.flush()
    if member:
        session.add(m.TeamMemberModel(team_id=team.id, user_id=user.id, role="employee"))
    cs = m.ClientSessionModel(user_id=user.id, status="active", started_at=NOW)
    session.add(cs)
    await session.flush()
    return user, team, other, cs


async def _add_meeting(session, team_id, *, scheduled_at, seq, state="scheduled", duration=60):
    meeting = m.MeetingModel(
        seq=seq,
        public_id=f"MTG-{seq}",
        team_id=team_id,
        title="Созвон",
        status=state,
        state=state,
        scheduled_at=scheduled_at,
        scheduled_timezone="Europe/Moscow",
        duration_minutes=duration,
        started_at=scheduled_at,
    )
    session.add(meeting)
    await session.flush()
    return meeting


@pytest.mark.asyncio
async def test_invalid_token_raises(session_factory):
    async with session_factory() as session:
        await _seed(session)
        await session.commit()
        with pytest.raises(DaemonAuthError):
            await resolve_daemon_state(session, "not-a-real-token", NOW, SETTINGS)


@pytest.mark.asyncio
async def test_no_meeting_is_idle(session_factory):
    async with session_factory() as session:
        _u, _t, _o, cs = await _seed(session)
        await session.commit()
        state = await resolve_daemon_state(session, str(cs.id), NOW, SETTINGS)
    assert state["state"] == "idle"
    assert state["meeting_id"] is None
    assert state["server_time"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_armed_before_meeting(session_factory):
    async with session_factory() as session:
        _u, team, _o, cs = await _seed(session)
        await _add_meeting(session, team.id, scheduled_at=NOW + timedelta(minutes=3), seq=1)
        await session.commit()
        state = await resolve_daemon_state(session, str(cs.id), NOW, SETTINGS)
    assert state["state"] == "armed"
    assert state["meeting_public_id"] == "MTG-1"
    assert str(team.id) == state["team_id"]


@pytest.mark.asyncio
async def test_recording_during_meeting(session_factory):
    async with session_factory() as session:
        _u, team, _o, cs = await _seed(session)
        await _add_meeting(session, team.id, scheduled_at=NOW - timedelta(minutes=10), seq=2)
        await session.commit()
        state = await resolve_daemon_state(session, str(cs.id), NOW, SETTINGS)
    assert state["state"] == "recording"
    assert state["recording_started_at"] is not None


@pytest.mark.asyncio
async def test_other_team_meeting_not_visible(session_factory):
    async with session_factory() as session:
        _u, _team, other, cs = await _seed(session)
        # Встреча идёт прямо сейчас, но в чужой команде (пользователь не участник).
        await _add_meeting(session, other.id, scheduled_at=NOW - timedelta(minutes=5), seq=3)
        await session.commit()
        state = await resolve_daemon_state(session, str(cs.id), NOW, SETTINGS)
    assert state["state"] == "idle"
    assert state["meeting_id"] is None
