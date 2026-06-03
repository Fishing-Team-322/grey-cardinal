from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from brain_api.api.deps import get_container, verify_internal_token
from brain_api.application.use_cases.desktop_client import (
    DesktopIdentity,
    confirm_desktop_proposal,
    desktop_tasks,
    gamification_state,
    heartbeat,
    ingest_desktop_transcript,
    join_meeting,
    leave_meeting,
    list_desktop_proposals,
    list_desktop_recent_transcripts,
    register_device,
    reject_desktop_proposal,
    resolve_desktop_identity,
)
from brain_api.container import Container
from grey_cardinal_contracts import (
    DesktopConfirmProposalResponse,
    DesktopGamificationStateResponse,
    DesktopHeartbeatRequest,
    DesktopHeartbeatResponse,
    DesktopProposalListResponse,
    DesktopRecentTranscriptsResponse,
    DesktopRejectProposalResponse,
    DesktopTaskListResponse,
    DesktopTranscriptRequest,
    JoinMeetingRequest,
    LeaveMeetingRequest,
    MeetingParticipantDTO,
    MeetingParticipantsResponse,
    RegisterDeviceRequest,
    RegisterDeviceResponse,
    StartClientSessionRequest,
    StartClientSessionResponse,
    TranscriptIngestResponse,
)

router = APIRouter(
    prefix="/desktop",
    tags=["desktop"],
    dependencies=[Depends(verify_internal_token)],
)


async def _identity(
    container: Container = Depends(get_container),
    x_gc_user_id: str | None = Header(default=None, alias="X-GC-User-Id"),
    x_gc_device_id: str | None = Header(default=None, alias="X-GC-Device-Id"),
    x_gc_client_session_id: str | None = Header(
        default=None, alias="X-GC-Client-Session-Id"
    ),
) -> DesktopIdentity:
    if not x_gc_user_id or not x_gc_device_id or not x_gc_client_session_id:
        raise HTTPException(status_code=401, detail="missing desktop identity headers")
    try:
        user_id = UUID(x_gc_user_id)
        device_id = UUID(x_gc_device_id)
        client_session_id = UUID(x_gc_client_session_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid desktop identity headers") from exc
    async with container.make_uow() as uow:
        try:
            return await resolve_desktop_identity(
                uow,
                user_id=user_id,
                device_id=device_id,
                client_session_id=client_session_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/devices/register", response_model=RegisterDeviceResponse)
async def register(
    request: RegisterDeviceRequest,
    container: Container = Depends(get_container),
) -> RegisterDeviceResponse:
    async with container.make_uow() as uow:
        return await register_device(uow, container.config, request)


@router.post("/sessions/start", response_model=StartClientSessionResponse)
async def start_session(
    request: StartClientSessionRequest,
    container: Container = Depends(get_container),
) -> StartClientSessionResponse:
    async with container.make_uow() as uow:
        user = await uow.users.get(UUID(request.user_id))
        device = await uow.devices.get(UUID(request.device_id))
        if user is None or device is None or device.user_id != user.id:
            raise HTTPException(status_code=404, detail="desktop user/device not found")
        session = await uow.client_sessions.start(
            user_id=user.id,
            device_id=device.id,
            workspace_id=UUID(request.workspace_id) if request.workspace_id else None,
            now=container.config.now(),
        )
        await uow.commit()
        return StartClientSessionResponse(client_session_id=str(session.id))


@router.post("/heartbeat", response_model=DesktopHeartbeatResponse)
async def desktop_heartbeat(
    request: DesktopHeartbeatRequest,
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> DesktopHeartbeatResponse:
    async with container.make_uow() as uow:
        return await heartbeat(uow, container.config, identity, request.meeting_public_id)


@router.post("/meetings/{meeting_public_id}/join", response_model=MeetingParticipantDTO)
async def join(
    meeting_public_id: str,
    request: JoinMeetingRequest,
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> MeetingParticipantDTO:
    async with container.make_uow() as uow:
        return await join_meeting(
            uow,
            container.config,
            identity,
            meeting_public_id,
            request.metadata,
        )


@router.post("/meetings/{meeting_public_id}/leave", response_model=MeetingParticipantDTO)
async def leave(
    meeting_public_id: str,
    request: LeaveMeetingRequest,
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> MeetingParticipantDTO:
    _ = request
    async with container.make_uow() as uow:
        try:
            return await leave_meeting(uow, container.config, identity, meeting_public_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/meetings/{meeting_public_id}/participants",
    response_model=MeetingParticipantsResponse,
)
async def participants(
    meeting_public_id: str,
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> MeetingParticipantsResponse:
    _ = identity
    async with container.make_uow() as uow:
        meeting = await uow.meetings.get_by_public_id(meeting_public_id)
        if meeting is None:
            raise HTTPException(status_code=404, detail="meeting not found")
        rows = await uow.meeting_participants.list_for_meeting(meeting.id)
        users = {row.user_id: await uow.users.get(row.user_id) for row in rows}
        return MeetingParticipantsResponse(
            items=[
                MeetingParticipantDTO(
                    id=str(row.id),
                    meeting_id=meeting.public_id,
                    user_id=str(row.user_id),
                    display_name=_display_name(users.get(row.user_id)),
                    device_id=str(row.device_id) if row.device_id else None,
                    client_session_id=str(row.client_session_id)
                    if row.client_session_id
                    else None,
                    status=row.status.value,
                    joined_at=row.joined_at,
                    left_at=row.left_at,
                    last_seen_at=row.last_seen_at,
                    metadata=row.metadata,
                )
                for row in rows
            ]
        )


def _display_name(user) -> str | None:
    return user.display_name if user is not None else None


@router.post("/transcripts", response_model=TranscriptIngestResponse)
async def transcript(
    request: DesktopTranscriptRequest,
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> TranscriptIngestResponse:
    async with container.make_uow() as uow:
        try:
            return await ingest_desktop_transcript(
                uow,
                container.extractor,
                container.telegram_gateway,
                container.event_publisher,
                container.config,
                identity,
                request,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks", response_model=DesktopTaskListResponse)
async def tasks(
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> DesktopTaskListResponse:
    async with container.make_uow() as uow:
        return await desktop_tasks(uow, identity)


@router.get("/gamification/me", response_model=DesktopGamificationStateResponse)
async def gamification(
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> DesktopGamificationStateResponse:
    async with container.make_uow() as uow:
        return await gamification_state(uow, identity)


@router.get("/proposals", response_model=DesktopProposalListResponse)
async def proposals(
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> DesktopProposalListResponse:
    """List pending task proposals for this user from desktop transcripts."""
    async with container.make_uow() as uow:
        return await list_desktop_proposals(uow, identity)


@router.post("/proposals/{proposal_id}/confirm", response_model=DesktopConfirmProposalResponse)
async def confirm_proposal(
    proposal_id: UUID,
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> DesktopConfirmProposalResponse:
    """Confirm a pending proposal, creating a task."""
    async with container.make_uow() as uow:
        try:
            return await confirm_desktop_proposal(
                uow, container.config, identity, proposal_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/reject", response_model=DesktopRejectProposalResponse)
async def reject_proposal(
    proposal_id: UUID,
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> DesktopRejectProposalResponse:
    """Reject a pending proposal."""
    async with container.make_uow() as uow:
        try:
            return await reject_desktop_proposal(uow, identity, proposal_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/transcripts/recent", response_model=DesktopRecentTranscriptsResponse)
async def recent_transcripts(
    limit: int = 20,
    identity: DesktopIdentity = Depends(_identity),
    container: Container = Depends(get_container),
) -> DesktopRecentTranscriptsResponse:
    """Return recent desktop transcript events for this user."""
    async with container.make_uow() as uow:
        return await list_desktop_recent_transcripts(uow, identity, limit=limit)
