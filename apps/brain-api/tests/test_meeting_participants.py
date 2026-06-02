from __future__ import annotations

from uuid import UUID

from brain_api.application.use_cases.desktop_client import (
    heartbeat,
    join_meeting,
    leave_meeting,
    resolve_desktop_identity,
)


async def _identity(make_uow, registered):
    async with make_uow() as uow:
        return await resolve_desktop_identity(
            uow,
            user_id=UUID(registered.user_id),
            device_id=UUID(registered.device_id),
            client_session_id=UUID(registered.client_session_id),
        )


async def test_join_meeting_creates_participant(register_desktop_identity, make_uow, config):
    registered = await register_desktop_identity()
    identity = await _identity(make_uow, registered)

    async with make_uow() as uow:
        participant = await join_meeting(uow, config, identity, "MTG-1")

    assert participant.meeting_id == "MTG-1"
    assert participant.status == "joined"
    assert participant.user_id == registered.user_id


async def test_heartbeat_updates_active_meeting_participant(
    register_desktop_identity, make_uow, config
):
    registered = await register_desktop_identity()
    identity = await _identity(make_uow, registered)
    async with make_uow() as uow:
        await join_meeting(uow, config, identity, "MTG-1")

    async with make_uow() as uow:
        response = await heartbeat(uow, config, identity, "MTG-1")

    assert response.active_meeting_id == "MTG-1"


async def test_leave_meeting_marks_participant_left(register_desktop_identity, make_uow, config):
    registered = await register_desktop_identity()
    identity = await _identity(make_uow, registered)
    async with make_uow() as uow:
        await join_meeting(uow, config, identity, "MTG-1")

    async with make_uow() as uow:
        participant = await leave_meeting(uow, config, identity, "MTG-1")

    assert participant.status == "left"
    assert participant.left_at is not None
