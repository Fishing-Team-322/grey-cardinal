"""Telegram → Telemost flow: ask provider, then create room on button click.

The bot must only *ask* on intent (never auto-create), and on confirmation it must
verify the chat is team-bound and Telemost is connected before creating a room.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from brain_api.api.routes import internal_telegram as itg
from brain_api.application.use_cases import yandex_telemost as svc
from brain_api.config import Settings
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher
from brain_api.integrations.yandex_telemost import TokenResponse
from grey_cardinal_contracts import (
    TelegramCallbackEvent,
    TelegramChatInfo,
    TelegramMessageEvent,
    TelegramMessageRef,
    TelegramSender,
)

CONFIGURED = Settings(
    yandex_telemost_client_id="cid",
    yandex_telemost_client_secret="sec",
    board_creds_encryption_key="unit-test-key",
)
CHAT_ID = -100123


class FakeClient:
    def build_authorization_url(self, state):  # pragma: no cover - unused here
        return "https://oauth.yandex.ru/authorize"

    async def refresh_token(self, rt):
        return TokenResponse("AT2", "RT2", 3600, "s", "bearer")

    async def create_conference(self, access_token, **kw):
        return {"id": "conf-9", "join_url": "https://telemost.yandex.ru/j/zzz"}


def _msg(text: str, chat_type: str = "supergroup") -> TelegramMessageEvent:
    return TelegramMessageEvent(
        update_id=1,
        message_id=10,
        chat=TelegramChatInfo(id=CHAT_ID, type=chat_type, title="Team chat"),
        sender=TelegramSender(id=555, username="boss", first_name="Boss"),
        text=text,
        date=datetime.now(UTC),
    )


def _callback(data: str) -> TelegramCallbackEvent:
    return TelegramCallbackEvent(
        update_id=2,
        callback_query_id="cq1",
        from_user=TelegramSender(id=555, username="boss", first_name="Boss"),
        message=TelegramMessageRef(message_id=11, chat_id=CHAT_ID),
        data=data,
    )


async def _seed_team(session, *, connected: bool):
    user = m.UserModel(id=uuid4(), display_name="Boss", telegram_user_id=555)
    session.add(user)
    company = m.CompanyModel(name="Co", timezone="Europe/Moscow", created_by=user.id)
    session.add(company)
    await session.flush()
    team = m.TeamModel(
        company_id=company.id, name="Team", timezone="Europe/Moscow", tg_chat_id=CHAT_ID
    )
    session.add(team)
    await session.flush()
    session.add(m.TeamMemberModel(team_id=team.id, user_id=user.id, role="manager"))
    if connected:
        cipher = SecretCipher(CONFIGURED.board_creds_encryption_key)
        session.add(
            m.YandexTelemostIntegrationModel(
                team_id=team.id,
                provider="yandex_telemost",
                status="connected",
                access_token_encrypted=cipher.encrypt_text("AT"),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    await session.commit()
    return team.id


def _texts(resp) -> str:
    return " | ".join(getattr(a, "text", "") for a in resp.actions)


@pytest.mark.asyncio
async def test_intent_asks_provider_without_creating() -> None:
    resp = await itg.ingest_message(_msg("нужен созвон"), container=SimpleNamespace())
    kbs = [
        getattr(a, "reply_markup", None)
        for a in resp.actions
        if getattr(a, "reply_markup", None)
    ]
    assert kbs, "expected an inline keyboard prompt"
    flat = str(kbs)
    assert "tmcall:create" in flat and "tmcall:dismiss" in flat
    assert "Телемост" in _texts(resp)


@pytest.mark.asyncio
async def test_non_call_message_does_not_prompt(monkeypatch) -> None:
    # A plain message must NOT trigger the Telemost prompt; it falls through to the
    # normal semantic path. We stub that path to confirm it's reached (and that the
    # response is not the tmcall keyboard).
    captured = {}

    async def fake_v2(event, container, **kw):
        captured["called"] = True
        from grey_cardinal_contracts import ActionsResponse

        return ActionsResponse(actions=[])

    monkeypatch.setattr(itg, "_try_v2_semantic_message", fake_v2)
    resp = await itg.ingest_message(_msg("доброе утро"), container=SimpleNamespace())
    assert captured.get("called") is True
    assert "tmcall:create" not in str([getattr(a, "reply_markup", None) for a in resp.actions])


@pytest.mark.asyncio
async def test_button_creates_room_and_posts_link(session_factory, monkeypatch) -> None:
    monkeypatch.setattr(itg, "get_settings", lambda: CONFIGURED)
    monkeypatch.setattr(svc, "build_client", lambda settings: FakeClient())
    async with session_factory() as session:
        await _seed_team(session, connected=True)

    container = SimpleNamespace(session_factory=session_factory)
    resp = await itg.ingest_callback(_callback("tmcall:create"), container=container)
    text = _texts(resp)
    assert "https://telemost.yandex.ru/j/zzz" in text
    assert "Телемост" in text
    assert "meeting agent" in text.lower()  # recording/notes notice present

    # a join job was queued
    async with session_factory() as session:
        from sqlalchemy import select

        jobs = (await session.execute(select(m.MeetingAgentJoinJobModel))).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].meeting_url == "https://telemost.yandex.ru/j/zzz"


@pytest.mark.asyncio
async def test_button_refuses_when_chat_not_bound(session_factory, monkeypatch) -> None:
    monkeypatch.setattr(itg, "get_settings", lambda: CONFIGURED)
    container = SimpleNamespace(session_factory=session_factory)
    resp = await itg.ingest_callback(_callback("tmcall:create"), container=container)
    assert "не привязан" in _texts(resp).lower()


@pytest.mark.asyncio
async def test_button_refuses_when_not_connected(session_factory, monkeypatch) -> None:
    monkeypatch.setattr(itg, "get_settings", lambda: CONFIGURED)
    async with session_factory() as session:
        await _seed_team(session, connected=False)
    container = SimpleNamespace(session_factory=session_factory)
    resp = await itg.ingest_callback(_callback("tmcall:create"), container=container)
    assert "не подключ" in _texts(resp).lower()


@pytest.mark.asyncio
async def test_dismiss(session_factory, monkeypatch) -> None:
    monkeypatch.setattr(itg, "get_settings", lambda: CONFIGURED)
    container = SimpleNamespace(session_factory=session_factory)
    resp = await itg.ingest_callback(_callback("tmcall:dismiss"), container=container)
    assert "без созвона" in _texts(resp).lower()
