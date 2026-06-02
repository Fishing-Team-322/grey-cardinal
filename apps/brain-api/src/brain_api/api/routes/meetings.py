from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.application.use_cases.manage_meetings import (
    meeting_response,
    start_meeting,
    stop_meeting,
)
from brain_api.container import Container
from grey_cardinal_contracts import (
    MeetingListResponse,
    MeetingStartRequest,
    MeetingStatusResponse,
    MeetingStopRequest,
)

router = APIRouter(
    prefix="/internal/meetings",
    tags=["internal-meetings"],
    dependencies=[Depends(verify_internal_token)],
)


@router.post("/start", response_model=MeetingStatusResponse)
async def start(
    request: MeetingStartRequest,
    container: Container = Depends(get_container),
) -> MeetingStatusResponse:
    async with container.make_uow() as uow:
        meeting = await start_meeting(
            uow,
            container.config,
            telegram_chat_id=request.telegram_chat_id,
            external_source=request.external_source,
            title=request.title,
            metadata=request.metadata,
        )
        await uow.commit()
        return await meeting_response(uow, meeting)


@router.post("/{meeting_public_id}/stop", response_model=MeetingStatusResponse)
async def stop(
    meeting_public_id: str,
    request: MeetingStopRequest,
    container: Container = Depends(get_container),
) -> MeetingStatusResponse:
    async with container.make_uow() as uow:
        meeting = await uow.meetings.get_by_public_id(meeting_public_id)
        if meeting is None:
            raise HTTPException(status_code=404, detail="Meeting not found")
        meeting = await stop_meeting(uow, container.config, meeting)
        await uow.commit()
        return await meeting_response(uow, meeting)


@router.get("/active", response_model=MeetingStatusResponse | None)
async def active(
    telegram_chat_id: int | None = None,
    container: Container = Depends(get_container),
) -> MeetingStatusResponse | None:
    async with container.make_uow() as uow:
        meeting = await uow.meetings.get_active_for_chat(telegram_chat_id)
        return await meeting_response(uow, meeting) if meeting else None


@router.get("/recent", response_model=MeetingListResponse)
async def recent(
    limit: int = 20,
    container: Container = Depends(get_container),
) -> MeetingListResponse:
    async with container.make_uow() as uow:
        meetings = await uow.meetings.list_recent(limit)
        return MeetingListResponse(
            items=[await meeting_response(uow, meeting) for meeting in meetings]
        )


@router.get("/{meeting_public_id}", response_model=MeetingStatusResponse)
async def get(
    meeting_public_id: str,
    container: Container = Depends(get_container),
) -> MeetingStatusResponse:
    async with container.make_uow() as uow:
        meeting = await uow.meetings.get_by_public_id(meeting_public_id)
        if meeting is None:
            raise HTTPException(status_code=404, detail="Meeting not found")
        return await meeting_response(uow, meeting)
