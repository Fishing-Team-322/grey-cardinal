from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from brain_api.api.routes import daemon
from brain_api.domain.enums import TaskSource
from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_daemon_upload_uses_valid_meeting_transcript_source(monkeypatch):
    user_id = uuid4()
    team_id = uuid4()
    captured = {}

    @asynccontextmanager
    async def session_factory():
        yield object()

    async def resolve_session(_session, _token):
        return SimpleNamespace(user_id=user_id)

    async def agent_team(_session, resolved_user_id):
        assert resolved_user_id == user_id
        return SimpleNamespace(id=team_id)

    async def ingest_team_text(_container, resolved_team_id, text, source):
        captured.update(team_id=resolved_team_id, text=text, source=source)
        return {"kind": "task_candidate", "proposal_created": True, "title": "Проверить релиз"}

    monkeypatch.setattr(daemon, "_resolve_session", resolve_session)
    monkeypatch.setattr(daemon, "_agent_team", agent_team)
    monkeypatch.setattr(daemon, "ingest_team_text", ingest_team_text)

    result = await daemon.daemon_v2_upload(
        audio=None,
        transcript_text="Проверить релиз сегодня",
        duration_sec=5,
        x_agent_token=str(uuid4()),
        container=SimpleNamespace(session_factory=session_factory),
    )

    assert result["proposal_created"] is True
    assert captured == {
        "team_id": team_id,
        "text": "Проверить релиз сегодня",
        "source": TaskSource.meeting_transcript,
    }


@pytest.mark.asyncio
async def test_agent_proposal_enters_web_ai_inbox_with_full_team_context(session_factory):
    captured = {}

    class Parser:
        async def parse(self, payload):
            captured["members"] = payload.team_members
            return {
                "kind": "task_candidate",
                "confidence": 0.93,
                "task": {
                    "title": "Подготовить релиз",
                    "assignee_text": "Denis",
                    "priority": "high",
                },
            }

    class Telegram:
        async def send_message(self, *args, **kwargs):
            captured["telegram"] = (args, kwargs)

    async with session_factory() as session:
        manager = m.UserModel(
            id=uuid4(),
            display_name="Denis Manager",
            email="denis@example.com",
            login="denis",
            telegram_username="denis_gc",
        )
        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=manager.id
        )
        team = m.TeamModel(
            id=uuid4(), company_id=company.id, name="Core", timezone="Europe/Moscow"
        )
        session.add_all([manager, company, team])
        await session.flush()
        session.add_all(
            [
                m.TeamMemberModel(
                    id=uuid4(), team_id=team.id, user_id=manager.id, role="manager"
                ),
                m.DeviceModel(
                    id=uuid4(),
                    user_id=manager.id,
                    device_name="Denis PC",
                    platform="windows",
                    last_seen_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()
        team_id = team.id

    container = SimpleNamespace(
        session_factory=session_factory,
        semantic_parser=Parser(),
        telegram_gateway=Telegram(),
        config=SimpleNamespace(task_extraction_min_confidence=0.5),
    )
    result = await daemon.ingest_team_text(
        container, team_id, "Денис, подготовь релиз", TaskSource.meeting_transcript
    )

    assert result["proposal_created"] is True
    assert any("Denis Manager" in item and "@denis_gc" in item for item in captured["members"])
    assert any("Windows agent: Denis PC" in item for item in captured["members"])
    assert "telegram" not in captured
    async with session_factory() as session:
        inbox = await session.scalar(select(m.AIInboxItemModel))
        confirmation = await session.scalar(select(m.ConfirmationModel))
        assert inbox is not None
        assert inbox.source_type == "daemon_proposal"
        assert inbox.source_id == str(confirmation.proposal_id)
        assert inbox.identity_payload["user_id"] == str(manager.id)
