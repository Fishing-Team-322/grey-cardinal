from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from brain_api.api.routes import daemon
from brain_api.domain.enums import TaskSource


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
