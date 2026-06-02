from __future__ import annotations

from uuid import UUID

from brain_api.application.use_cases.desktop_client import heartbeat, resolve_desktop_identity
from brain_api.infrastructure.db import models as m


async def test_register_device_creates_user_device_session(
    register_desktop_identity, session_factory
):
    identity = await register_desktop_identity()

    assert UUID(identity.user_id)
    assert UUID(identity.device_id)
    assert UUID(identity.client_session_id)
    assert identity.workspace_id is not None

    async with session_factory() as session:
        user = await session.get(m.UserModel, UUID(identity.user_id))
        device = await session.get(m.DeviceModel, UUID(identity.device_id))
        client_session = await session.get(
            m.ClientSessionModel, UUID(identity.client_session_id)
        )

    assert user is not None
    assert user.display_name == "Петя"
    assert device is not None
    assert device.platform == "windows"
    assert client_session is not None
    assert client_session.status == "active"


async def test_desktop_heartbeat_updates_last_seen(register_desktop_identity, make_uow, config):
    registered = await register_desktop_identity()
    async with make_uow() as uow:
        identity = await resolve_desktop_identity(
            uow,
            user_id=UUID(registered.user_id),
            device_id=UUID(registered.device_id),
            client_session_id=UUID(registered.client_session_id),
        )
        response = await heartbeat(uow, config, identity)

    assert response.ok is True
    async with make_uow() as uow:
        device = await uow.devices.get(UUID(registered.device_id))
        session = await uow.client_sessions.get(UUID(registered.client_session_id))

    assert device is not None and device.last_seen_at is not None
    assert session is not None and session.last_seen_at is not None
