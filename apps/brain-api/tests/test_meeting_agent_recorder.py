from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from brain_api.api.routes import meeting_agent
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.events.event_bus import NullEventPublisher
from brain_api.infrastructure.telegram_gateway.client import NullTelegramGateway


async def _seed(session_factory, status: str = "queued"):
    async with session_factory() as session:
        user = m.UserModel(display_name="Manager")
        session.add(user)
        await session.flush()
        company = m.CompanyModel(name="Co", timezone="Europe/Moscow", created_by=user.id)
        session.add(company)
        await session.flush()
        team = m.TeamModel(
            company_id=company.id,
            name="Team",
            timezone="Europe/Moscow",
            tg_chat_id=-100123,
        )
        session.add(team)
        await session.flush()
        meeting = m.MeetingModel(
            seq=1,
            public_id="MTG-1",
            team_id=team.id,
            title="Telemost",
            status="scheduled",
            state="scheduled",
            scheduled_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
        )
        session.add(meeting)
        await session.flush()
        job = m.MeetingAgentJoinJobModel(
            team_id=team.id,
            provider="yandex_telemost",
            meeting_url="https://telemost.yandex.ru/j/1",
            meeting_id=meeting.id,
            telegram_chat_id=team.tg_chat_id,
            status=status,
        )
        session.add(job)
        await session.commit()
        return job.id, meeting.id


def _container(session_factory):
    return SimpleNamespace(
        session_factory=session_factory,
        telegram_gateway=NullTelegramGateway(),
        event_publisher=NullEventPublisher(),
    )


@pytest.mark.asyncio
async def test_claim_record_complete_lifecycle(session_factory) -> None:
    job_id, meeting_id = await _seed(session_factory)
    container = _container(session_factory)
    body = meeting_agent.WorkerBody(worker_id="worker-1")

    claimed = await meeting_agent.claim_job(body, container)
    assert claimed["id"] == str(job_id)
    assert claimed["meeting_public_id"] == "MTG-1"
    assert claimed["status"] == "joining"

    recording = await meeting_agent.mark_recording(job_id, body, container)
    assert recording["status"] == "recording"
    assert "начал запись" in container.telegram_gateway.sent[-1][1]

    completed = await meeting_agent.complete_job(job_id, body, container)
    assert completed["status"] == "completed"
    async with session_factory() as session:
        meeting = await session.get(m.MeetingModel, meeting_id)
        assert meeting.state == "stopped"
        assert meeting.status == "stopped"
        assert meeting.stopped_at is not None


@pytest.mark.asyncio
async def test_claim_is_atomic_and_skips_owned_job(session_factory) -> None:
    await _seed(session_factory)
    container = _container(session_factory)
    first = await meeting_agent.claim_job(
        meeting_agent.WorkerBody(worker_id="worker-1"), container
    )
    second = await meeting_agent.claim_job(
        meeting_agent.WorkerBody(worker_id="worker-2"), container
    )
    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_wrong_worker_cannot_update_job(session_factory) -> None:
    job_id, _ = await _seed(session_factory)
    container = _container(session_factory)
    await meeting_agent.claim_job(meeting_agent.WorkerBody(worker_id="worker-1"), container)
    with pytest.raises(Exception) as exc:
        await meeting_agent.heartbeat(
            job_id, meeting_agent.WorkerBody(worker_id="worker-2"), container
        )
    assert getattr(exc.value, "status_code", None) == 409
