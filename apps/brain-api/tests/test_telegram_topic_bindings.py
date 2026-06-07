# ruff: noqa: E501
from __future__ import annotations

from uuid import uuid4

import pytest
from agentic_pm_test_utils import seed_pm

from brain_api.infrastructure.db import models as m


@pytest.mark.asyncio
async def test_telegram_topic_binding_schema_links_thread_to_team(session_factory):
    seeded = await seed_pm(session_factory)
    async with session_factory() as session:
        chat = m.TelegramChatModel(id=uuid4(), team_id=seeded["team_id"], telegram_chat_id=-100, type="supergroup", title="Chat")
        session.add(chat)
        await session.flush()
        binding = m.TelegramTopicBindingModel(id=uuid4(), telegram_chat_id=chat.id, message_thread_id=42, team_id=seeded["team_id"], source_name="Backend topic")
        session.add(binding)
        await session.commit()

    assert binding.message_thread_id == 42
