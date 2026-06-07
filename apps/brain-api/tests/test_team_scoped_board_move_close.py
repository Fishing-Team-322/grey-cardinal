"""Item 8: move/close/comment должны идти в адаптер доски нужной команды."""

from __future__ import annotations

from uuid import uuid4

import pytest

from brain_api.config import Settings
from brain_api.domain.enums import TaskStatus
from brain_api.infrastructure.board.factory import BoardAdapterFactory, TeamScopedBoardGateway
from brain_api.infrastructure.db import models as m

TEAM_A = uuid4()


class _RecAdapter:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    async def move_card(self, ext, status):
        self.calls.append((self.name, "move", ext))

    async def close_card(self, ext):
        self.calls.append((self.name, "close", ext))

    async def add_comment(self, ext, text):
        self.calls.append((self.name, "comment", ext))


async def _seed_card(session_factory, *, external, team_id):
    async with session_factory() as session:
        session.add(
            m.BoardCardModel(
                team_id=team_id,
                task_id=uuid4(),
                provider="yougile",
                external_card_id=external,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_move_uses_team_adapter(session_factory):
    await _seed_card(session_factory, external="EXT-A", team_id=TEAM_A)
    calls: list = []
    factory = BoardAdapterFactory(session_factory, Settings())

    async def fake_for_team(team_id):
        calls.append(("for_team", team_id))
        return _RecAdapter("team", calls)

    factory.for_team = fake_for_team  # type: ignore[assignment]
    gw = TeamScopedBoardGateway(factory, _RecAdapter("fallback", calls))

    await gw.move_card("EXT-A", TaskStatus.done)
    assert ("for_team", TEAM_A) in calls
    assert ("team", "move", "EXT-A") in calls
    assert not any(c[0] == "fallback" for c in calls)


@pytest.mark.asyncio
async def test_unknown_card_falls_back(session_factory):
    calls: list = []
    factory = BoardAdapterFactory(session_factory, Settings())

    async def fake_for_team(team_id):
        calls.append(("for_team", team_id))
        return _RecAdapter("team", calls)

    factory.for_team = fake_for_team  # type: ignore[assignment]
    gw = TeamScopedBoardGateway(factory, _RecAdapter("fallback", calls))

    await gw.close_card("EXT-UNKNOWN")
    assert ("fallback", "close", "EXT-UNKNOWN") in calls
    assert not any(c[0] == "for_team" for c in calls)
