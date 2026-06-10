"""LLM-first semantic parser for team chat messages.

Pipeline:
    SemanticMessageParser
      -> NoisePreFilter           (отсекает очевидный мусор без LLM)
      -> LLMProviderFactory.resolve_for_team(team_id)
      -> Primary provider         (retry на invalid JSON / schema error)
      -> Fallback provider        (timeout / 429 / 5xx / invalid JSON / unavailable)
      -> Pydantic validation      (strict JSON)
      -> SemanticParseResult (dict-контракт semantic_message_v2)

Если LLM-провайдер вообще не настроен — мягкая деградация на эвристику, чтобы
бот не «молчал». Если настроен, но и primary, и fallback не дали валидного
ответа — возвращаем controlled ``semantic_parse_failed`` (downstream не создаёт
задачи и не спамит чат).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError

from brain_api.application.llm.noise_prefilter import NoisePreFilter
from brain_api.application.llm.schema import SemanticParseResult, semantic_json_schema
from brain_api.infrastructure.llm.errors import LLMError
from brain_api.infrastructure.llm.prompts import build_semantic_prompt
from brain_api.infrastructure.llm.providers import LLMProvider, ResolvedLLM

logger = logging.getLogger(__name__)
metrics_logger = logging.getLogger("brain_api.llm.metrics")

SEMANTIC_KINDS = {
    "task_candidate",
    "task_reassignment",
    "task_cancellation",
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
    sender_display_name: str | None = None
    team_members: list[str] = field(default_factory=list)
    interaction_mode: str = "AUTO_BACKGROUND"
    reply_to_text: str | None = None
    reply_to_sender_display_name: str | None = None
    recent_messages: list[dict] = field(default_factory=list)


class SemanticParseFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class _ProviderRun:
    """Итог одного прогона провайдера (с ретраями) для метрик."""

    result: SemanticParseResult | None
    retry_count: int
    validation_error: bool


class SemanticMessageParser:
    def __init__(
        self,
        provider_factory: object,
        prefilter: NoisePreFilter | None = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._prefilter = prefilter or NoisePreFilter()

    async def parse(self, payload: SemanticMessageInput) -> dict:
        # 0. Дешёвый pre-filter: очевидный Telegram-шум не гоняем в LLM.
        pre = self._prefilter.check(payload.message_text)
        if pre.is_noise:
            return {
                "kind": "noise",
                "confidence": 1.0,
                "task": None,
                "meeting": None,
                "daily_report": None,
                "absence": None,
                "reassignment": None,
                "cancellation": None,
                "affect": None,
                "reason": "prefilter",
            }

        # 1. Резолвим primary + fallback. Если LLM не настроен — эвристика.
        try:
            resolved = await self._resolve(payload.team_id)
        except Exception as exc:  # noqa: BLE001 — любая проблема резолва => эвристика
            logger.info(
                "No LLM provider for team_id=%s (%s); using heuristic fallback",
                payload.team_id,
                exc,
            )
            return self._heuristic(payload)

        prompt = self._build_prompt(payload)

        # 2. Primary с ретраями.
        run = await self._run_provider(resolved.primary, prompt, payload, "primary")
        if run.result is not None:
            self._log_metrics(
                payload, run.result.kind, fallback_used=False,
                retry_count=run.retry_count, validation_error=run.validation_error,
            )
            return run.result.to_contract_dict()

        # 3. Fallback с ретраями (только если primary не справился).
        if resolved.fallback is not None:
            run = await self._run_provider(
                resolved.fallback, prompt, payload, "fallback"
            )
            if run.result is not None:
                self._log_metrics(
                    payload, run.result.kind, fallback_used=True,
                    retry_count=run.retry_count, validation_error=run.validation_error,
                )
                return run.result.to_contract_dict()

        # 4. Оба провайдера не дали валидного ответа — controlled failure.
        logger.warning(
            "Semantic parse failed for team_id=%s (primary+fallback exhausted)",
            payload.team_id,
        )
        self._log_metrics(
            payload, "semantic_parse_failed", fallback_used=True, error=True,
            retry_count=run.retry_count, validation_error=run.validation_error,
        )
        return {
            "kind": "semantic_parse_failed",
            "confidence": 0.0,
            "task": None,
            "meeting": None,
            "daily_report": None,
            "absence": None,
            "reassignment": None,
            "cancellation": None,
            "affect": None,
            "reason": "primary and fallback providers failed",
        }

    async def _resolve(self, team_id: UUID) -> ResolvedLLM:
        factory = self._provider_factory
        if hasattr(factory, "resolve_for_team"):
            return await factory.resolve_for_team(team_id)  # type: ignore[no-any-return]
        # Совместимость со старыми фейками: только primary.
        provider = await factory.for_team(team_id)  # type: ignore[attr-defined]
        return ResolvedLLM(primary=provider, fallback=None)

    async def _run_provider(
        self,
        provider: LLMProvider,
        prompt: str,
        payload: SemanticMessageInput,
        role: str,
    ) -> _ProviderRun:
        max_retries = getattr(getattr(provider, "config", None), "max_retries", 2) or 0
        json_schema = semantic_json_schema()
        last_error: Exception | None = None
        validation_error = False
        for attempt in range(max_retries + 1):
            try:
                raw = await provider.complete_json(
                    prompt, "semantic_message_v2", json_schema=json_schema
                )
                return _ProviderRun(
                    result=SemanticParseResult.model_validate(raw),
                    retry_count=attempt,
                    validation_error=validation_error,
                )
            except LLMError as exc:
                # Сетевые/HTTP/JSON ошибки провайдера — ретраим, затем fallback.
                last_error = exc
                logger.warning(
                    "LLM %s provider error (team_id=%s attempt=%s cat=%s): %s",
                    role, payload.team_id, attempt + 1, exc.category, exc,
                )
            except ValidationError as exc:
                last_error = exc
                validation_error = True
                logger.warning(
                    "LLM %s schema validation failed (team_id=%s attempt=%s): %s",
                    role, payload.team_id, attempt + 1, exc,
                )
        logger.warning(
            "LLM %s exhausted retries (team_id=%s): %s",
            role, payload.team_id, last_error,
        )
        return _ProviderRun(
            result=None, retry_count=max_retries, validation_error=validation_error
        )

    def _heuristic(self, payload: SemanticMessageInput) -> dict:
        from brain_api.application.heuristic_semantic import classify_message

        return classify_message(
            text=payload.message_text,
            now=payload.now,
            timezone=payload.team_timezone,
        )

    def _build_prompt(self, payload: SemanticMessageInput) -> str:
        return build_semantic_prompt(
            message_text=payload.message_text,
            now=payload.now,
            timezone=payload.team_timezone,
            sender_display_name=payload.sender_display_name,
            team_members=payload.team_members,
            interaction_mode=payload.interaction_mode,
            reply_to_text=payload.reply_to_text,
            reply_to_sender_display_name=payload.reply_to_sender_display_name,
            recent_messages=payload.recent_messages,
        )

    def _log_metrics(
        self,
        payload: SemanticMessageInput,
        kind: str,
        *,
        fallback_used: bool,
        error: bool = False,
        retry_count: int = 0,
        validation_error: bool = False,
    ) -> None:
        # Безопасные структурированные метрики: НЕ логируем текст сообщения
        # (кроме debug) и тем более API-ключи/Authorization.
        metrics_logger.info(
            "semantic_parse team_id=%s semantic_kind=%s fallback_used=%s error=%s "
            "validation_error=%s retry_count=%s",
            payload.team_id, kind, fallback_used, error, validation_error, retry_count,
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "semantic_parse text=%r (team_id=%s)",
                payload.message_text, payload.team_id,
            )
