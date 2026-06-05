"""LLM-экстрактор задач поверх OpenAI-совместимого клиента.

Если LLM недоступен/ответ некорректен — мягкий фолбэк на HeuristicTaskExtractor,
чтобы pipeline никогда не падал из-за внешней модели.
"""

from __future__ import annotations

import json
import logging
from contextlib import suppress
from datetime import datetime

from brain_api.infrastructure.llm.client import OpenAICompatibleClient
from brain_api.infrastructure.llm.heuristic_extractor import HeuristicTaskExtractor
from brain_api.infrastructure.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from grey_cardinal_contracts import KnownUser, TaskExtractionResult, TaskPriority

logger = logging.getLogger(__name__)


class LLMTaskExtractor:
    def __init__(
        self,
        client: OpenAICompatibleClient,
        fallback: HeuristicTaskExtractor | None = None,
    ) -> None:
        self._client = client
        self._fallback = fallback or HeuristicTaskExtractor()

    async def extract_task(
        self,
        text: str,
        now: datetime,
        timezone: str,
        known_users: list[KnownUser],
        conversation_context: str | None = None,
    ) -> TaskExtractionResult:
        user_prompt = build_user_prompt(text, now, timezone, known_users, conversation_context)
        try:
            raw = await self._client.chat(SYSTEM_PROMPT, user_prompt)
            return _parse(raw)
        except Exception as exc:  # сеть/JSON/таймаут — не валим pipeline
            logger.warning("LLM extraction failed, falling back to heuristic: %s", exc)
            return await self._fallback.extract_task(
                text, now, timezone, known_users, conversation_context
            )


def _parse(raw: str) -> TaskExtractionResult:
    data = json.loads(raw)
    if not data.get("has_task"):
        return TaskExtractionResult(has_task=False, reason=data.get("reason"))

    deadline = None
    if data.get("deadline"):
        try:
            deadline = datetime.fromisoformat(str(data["deadline"]))
        except ValueError:
            deadline = None

    priority = TaskPriority.medium
    with suppress(ValueError):
        priority = TaskPriority(str(data.get("priority", "medium")))

    return TaskExtractionResult(
        has_task=True,
        title=data.get("title"),
        description=data.get("description"),
        assignee=data.get("assignee"),
        deadline=deadline,
        priority=priority,
        confidence=float(data.get("confidence", 0.7)),
        reason=data.get("reason"),
    )
