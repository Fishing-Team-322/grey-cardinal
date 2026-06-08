"""Internal queue API for the visible Telemost recording participant."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.container import Container
from brain_api.infrastructure.db import models as m
from grey_cardinal_contracts import EventName, WebsocketEvent

router = APIRouter(
    prefix="/internal/meeting-agent",
    tags=["internal-meeting-agent"],
    dependencies=[Depends(verify_internal_token)],
)

STALE_AFTER = timedelta(minutes=2)
MAX_ATTEMPTS = 3


class WorkerBody(BaseModel):
    worker_id: str


class FailureBody(WorkerBody):
    error_message: str


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _payload(job: m.MeetingAgentJoinJobModel, meeting: m.MeetingModel) -> dict:
    return {
        "id": str(job.id),
        "status": job.status,
        "meeting_url": job.meeting_url,
        "conference_id": job.conference_id,
        "meeting_id": str(meeting.id),
        "meeting_public_id": meeting.public_id,
        "telegram_chat_id": job.telegram_chat_id,
        "attempts": job.attempts,
        "stop_requested": job.status == "stop_requested",
    }


async def _owned_job(session, job_id: UUID, worker_id: str) -> m.MeetingAgentJoinJobModel:
    job = await session.get(m.MeetingAgentJoinJobModel, job_id)
    if job is None:
        raise HTTPException(404, "Recording job not found")
    if job.worker_id != worker_id:
        raise HTTPException(409, "Recording job is owned by another worker")
    return job


@router.post("/jobs/claim")
async def claim_job(
    body: WorkerBody,
    container: Container = Depends(get_container),
) -> dict | None:
    now = datetime.now(UTC)
    async with container.session_factory() as session, session.begin():
        stale = (
            await session.execute(
                select(m.MeetingAgentJoinJobModel)
                .where(
                    m.MeetingAgentJoinJobModel.status.in_(["joining", "recording"]),
                    m.MeetingAgentJoinJobModel.heartbeat_at.is_not(None),
                )
                .with_for_update(skip_locked=True)
            )
        ).scalars()
        for item in stale:
            heartbeat = _as_utc(item.heartbeat_at)
            if heartbeat and heartbeat < now - STALE_AFTER:
                item.status = "queued" if item.attempts < MAX_ATTEMPTS else "failed"
                item.error_message = "Recorder heartbeat timed out"
                item.worker_id = None

        job = await session.scalar(
            select(m.MeetingAgentJoinJobModel)
            .where(
                m.MeetingAgentJoinJobModel.provider == "yandex_telemost",
                m.MeetingAgentJoinJobModel.status == "queued",
                m.MeetingAgentJoinJobModel.meeting_id.is_not(None),
                m.MeetingAgentJoinJobModel.attempts < MAX_ATTEMPTS,
            )
            .order_by(m.MeetingAgentJoinJobModel.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        meeting = await session.get(m.MeetingModel, job.meeting_id)
        if meeting is None:
            job.status = "failed"
            job.error_message = "Linked meeting not found"
            return None
        job.status = "joining"
        job.worker_id = body.worker_id
        job.attempts += 1
        job.heartbeat_at = now
        job.error_message = None
        return _payload(job, meeting)


@router.post("/jobs/{job_id}/recording")
async def mark_recording(
    job_id: UUID,
    body: WorkerBody,
    container: Container = Depends(get_container),
) -> dict:
    now = datetime.now(UTC)
    async with container.session_factory() as session:
        job = await _owned_job(session, job_id, body.worker_id)
        meeting = await session.get(m.MeetingModel, job.meeting_id)
        if meeting is None:
            raise HTTPException(409, "Linked meeting not found")
        job.status = "recording"
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        meeting.state = "recording"
        meeting.status = "active"
        meeting.started_at = meeting.started_at or now
        await session.commit()
        payload = _payload(job, meeting)
    if job.telegram_chat_id is not None:
        await container.telegram_gateway.send_message(
            job.telegram_chat_id,
            "🔴 Grey Cardinal подключился к Телемосту как видимый участник и начал запись. "
            "Микрофон и камера агента выключены.",
        )
    await container.event_publisher.publish(
        WebsocketEvent(
            event=EventName.meeting_recording_started,
            payload={"meeting_id": str(meeting.id), "meeting_public_id": meeting.public_id},
        )
    )
    return payload


@router.post("/jobs/{job_id}/heartbeat")
async def heartbeat(
    job_id: UUID,
    body: WorkerBody,
    container: Container = Depends(get_container),
) -> dict:
    async with container.session_factory() as session:
        job = await _owned_job(session, job_id, body.worker_id)
        meeting = await session.get(m.MeetingModel, job.meeting_id)
        if meeting is None:
            raise HTTPException(409, "Linked meeting not found")
        job.heartbeat_at = datetime.now(UTC)
        await session.commit()
        return _payload(job, meeting)


@router.post("/jobs/{job_id}/complete")
async def complete_job(
    job_id: UUID,
    body: WorkerBody,
    container: Container = Depends(get_container),
) -> dict:
    now = datetime.now(UTC)
    async with container.session_factory() as session:
        job = await _owned_job(session, job_id, body.worker_id)
        meeting = await session.get(m.MeetingModel, job.meeting_id)
        if meeting is None:
            raise HTTPException(409, "Linked meeting not found")
        job.status = "completed"
        job.completed_at = now
        job.heartbeat_at = now
        # The scheduled finalizer turns stopped meetings into finished meetings
        # and builds the summary on its next run.
        meeting.state = "stopped"
        meeting.status = "stopped"
        meeting.stopped_at = now
        await session.commit()
        payload = _payload(job, meeting)
    if job.telegram_chat_id is not None:
        await container.telegram_gateway.send_message(
            job.telegram_chat_id,
            "✅ Grey Cardinal завершил запись Телемоста. Транскрипт и задачи обрабатываются.",
        )
    await container.event_publisher.publish(
        WebsocketEvent(
            event=EventName.meeting_finished,
            payload={"meeting_id": str(meeting.id), "meeting_public_id": meeting.public_id},
        )
    )
    return payload


@router.post("/jobs/{job_id}/fail")
async def fail_job(
    job_id: UUID,
    body: FailureBody,
    container: Container = Depends(get_container),
) -> dict:
    async with container.session_factory() as session:
        job = await _owned_job(session, job_id, body.worker_id)
        meeting = await session.get(m.MeetingModel, job.meeting_id)
        if meeting is None:
            raise HTTPException(409, "Linked meeting not found")
        job.status = "failed"
        job.error_message = body.error_message[:1000]
        job.completed_at = datetime.now(UTC)
        await session.commit()
        payload = _payload(job, meeting)
    if job.telegram_chat_id is not None:
        await container.telegram_gateway.send_message(
            job.telegram_chat_id,
            "⚠️ Агент записи не смог продолжить запись Телемоста. "
            "Запись через установленные приложения продолжает работать.",
        )
    return payload
