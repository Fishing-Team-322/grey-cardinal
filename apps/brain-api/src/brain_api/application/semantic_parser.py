"""LLM-first semantic parser for team chat messages."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from brain_api.infrastructure.llm.providers import LLMProviderFactory

logger = logging.getLogger(__name__)

SEMANTIC_KINDS = {
    "task_candidate",
    "meeting_candidate",
    "daily_report",
    "absence_notice",
    "status_update",
    "question",
    "noise",
    "unknown",
}


@dataclass(frozen=True)
class SemanticMessageInput:
    team_id: UUID
    message_text: str
    sender_user_id: UUID | None
    team_timezone: str
    now: datetime


class SemanticParseFailed(RuntimeError):
    pass


class SemanticMessageParser:
    def __init__(self, provider_factory: LLMProviderFactory) -> None:
        self._provider_factory = provider_factory

    async def parse(self, payload: SemanticMessageInput) -> dict:
        # 1. Резолвим LLM-провайдера команды. Если LLM не настроен — сразу
        #    эвристический fallback (бот не должен «молчать» без LLM).
        try:
            provider = await self._provider_factory.for_team(payload.team_id)
        except Exception as exc:  # noqa: BLE001 — любая проблема резолва => fallback
            logger.info(
                "No LLM provider for team_id=%s (%s); using heuristic fallback",
                payload.team_id,
                exc,
            )
            return self._heuristic(payload)

        max_retries = getattr(getattr(provider, "config", None), "max_retries", 2)
        prompt = self._build_prompt(payload)
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                result = self._validate(await provider.complete_json(prompt, "semantic_message_v2"))
                return self._merge_with_heuristic(payload, result)
            except Exception as exc:  # noqa: BLE001 — сеть/JSON/валидация => retry/fallback
                last_error = exc
                logger.warning(
                    "Semantic parse failed (team_id=%s attempt=%s): %s",
                    payload.team_id,
                    attempt + 1,
                    exc,
                )
        # 2. LLM не справился после ретраев — деградируем на эвристику, а не падаем.
        logger.warning(
            "LLM semantic parse exhausted retries (team_id=%s): %s; heuristic fallback",
            payload.team_id,
            last_error,
        )
        return self._heuristic(payload)

    def _heuristic(self, payload: SemanticMessageInput) -> dict:
        from brain_api.application.heuristic_semantic import classify_message

        return classify_message(
            text=payload.message_text,
            now=payload.now,
            timezone=payload.team_timezone,
        )

    def _merge_with_heuristic(self, payload: SemanticMessageInput, llm_result: dict) -> dict:
        """Маленькие локальные LLM часто помечают явные задачи/созвоны как noise.
        Если LLM сказал noise/unknown/question, а эвристика уверенно видит
        задачу или созвон — берём эвристику (так «Эй Саня, надо собрать…» не теряется).
        """
        if llm_result.get("kind") not in ("noise", "unknown", "question"):
            return llm_result
        heur = self._heuristic(payload)
        if heur["kind"] in ("task_candidate", "meeting_candidate") and heur["confidence"] >= 0.6:
            logger.info(
                "LLM=%s overridden by heuristic=%s (team_id=%s)",
                llm_result.get("kind"), heur["kind"], payload.team_id,
            )
            return heur
        return llm_result

    def _build_prompt(self, payload: SemanticMessageInput) -> str:
        return (
            "Classify this Telegram team-chat message for Grey Cardinal v2.\n"
            f"team_id: {payload.team_id}\n"
            f"sender_user_id: {payload.sender_user_id}\n"
            f"team_timezone: {payload.team_timezone}\n"
            f"now: {payload.now.isoformat()}\n"
            "Return strict JSON with keys: kind, confidence, task, meeting, "
            "daily_report, absence, reason. Dates must be ISO-8601 and interpreted "
            "in team_timezone when the message uses relative local time.\n"
            f"message: {payload.message_text}"
        )

    def _validate(self, result: dict) -> dict:
        kind = result.get("kind", "unknown")
        if kind not in SEMANTIC_KINDS:
            raise ValueError(f"Unknown semantic kind: {kind}")
        confidence = float(result.get("confidence", 0.0))
        if confidence < 0 or confidence > 1:
            raise ValueError("confidence must be between 0 and 1")
        result["kind"] = kind
        result["confidence"] = confidence
        result.setdefault("task", None)
        result.setdefault("meeting", None)
        result.setdefault("daily_report", None)
        result.setdefault("absence", None)
        result.setdefault("reason", "")
        return result
