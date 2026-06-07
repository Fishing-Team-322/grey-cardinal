"""LLM-провайдеры для v2 semantic pipeline.

Стратегия:
  * Primary  — Groq direct (external_api, OpenAI-совместимый).
  * Fallback — OpenRouter (external_api).
  * Local    — Ollama, только dev/privacy mode.

Провайдер:
  * использует ``response_format`` (json_schema -> json_object downgrade);
  * классифицирует ошибки (timeout / 429 / 5xx / invalid JSON / unavailable);
  * пишет безопасные метрики (без API-ключей и Authorization).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain_api.config import Settings
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.llm.errors import (
    LLMError,
    LLMInvalidJSONError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from brain_api.infrastructure.security.encryption import SecretCipher

logger = logging.getLogger(__name__)
metrics_logger = logging.getLogger("brain_api.llm.metrics")


def friendly_provider_name(base_url: str) -> str:
    """Человекочитаемое имя провайдера по base_url (для health/метрик)."""
    host = (base_url or "").lower()
    if "groq.com" in host:
        return "groq"
    if "openrouter.ai" in host:
        return "openrouter"
    if "ollama" in host or ":11434" in host:
        return "ollama"
    if "openai.com" in host:
        return "openai"
    return "external_api"


class LLMProvider(Protocol):
    config: LLMProviderConfig

    async def complete_json(
        self, prompt: str, schema_name: str, *, json_schema: dict | None = None
    ) -> dict: ...


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: int
    max_retries: int
    strict_json: bool
    # HTTP(S)-прокси для исходящих LLM-запросов. Нужен, когда IP сервера
    # гео-блокируется провайдером (напр. Groq отдаёт 403 для части регионов).
    # Берётся из LLM_PROXY; секрет в логи/health не попадает.
    proxy: str | None = None
    # transport не участвует в сравнении/хешировании — только для тестов.
    transport: httpx.AsyncBaseTransport | None = field(
        default=None, compare=False, hash=False, repr=False
    )

    @property
    def label(self) -> str:
        return friendly_provider_name(self.base_url)


@dataclass(frozen=True)
class ResolvedLLM:
    """Разрешённая для команды связка primary + optional fallback."""

    primary: LLMProvider
    fallback: LLMProvider | None = None


class OpenAICompatibleJSONProvider:
    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.label

    def _build_payload(self, prompt: str, schema_name: str, response_format: dict) -> dict:
        return {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only strict JSON for the requested Grey Cardinal schema. "
                        f"Schema name: {schema_name}."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": response_format,
        }

    async def complete_json(
        self, prompt: str, schema_name: str, *, json_schema: dict | None = None
    ) -> dict:
        started = time.perf_counter()
        try:
            content = await self._request(prompt, schema_name, json_schema)
            parsed = self._parse(content)
            self._log(started, success=True)
            return parsed
        except LLMError as exc:
            self._log(started, success=False, error=exc.category)
            raise

    async def _request(
        self, prompt: str, schema_name: str, json_schema: dict | None
    ) -> str:
        use_schema = json_schema is not None
        response_format: dict = (
            {"type": "json_schema", "json_schema": json_schema}
            if use_schema
            else {"type": "json_object"}
        )
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"

        client_kwargs: dict = {"timeout": self.config.timeout_seconds}
        if self.config.transport is not None:
            # В тестах используется MockTransport (proxy с ним несовместим).
            client_kwargs["transport"] = self.config.transport
        elif self.config.proxy:
            client_kwargs["proxy"] = self.config.proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            try:
                response = await client.post(
                    url,
                    json=self._build_payload(prompt, schema_name, response_format),
                    headers=headers,
                )
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise LLMUnavailableError(str(exc)) from exc

            # Провайдер/модель не поддерживает json_schema -> мягкий downgrade.
            if response.status_code == 400 and use_schema:
                try:
                    response = await client.post(
                        url,
                        json=self._build_payload(
                            prompt, schema_name, {"type": "json_object"}
                        ),
                        headers=headers,
                    )
                except httpx.TimeoutException as exc:
                    raise LLMTimeoutError(str(exc)) from exc
                except httpx.HTTPError as exc:
                    raise LLMUnavailableError(str(exc)) from exc

            self._raise_for_status(response)
            data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMInvalidJSONError(f"unexpected response shape: {exc}") from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        code = response.status_code
        if code == 429:
            raise LLMRateLimitError("HTTP 429 rate limited")
        if 500 <= code < 600:
            raise LLMServerError(f"HTTP {code} server error")
        if code >= 400:
            # 4xx (incl. 400 после downgrade) — считаем провайдер непригодным.
            raise LLMUnavailableError(f"HTTP {code} client error")

    @staticmethod
    def _parse(content: str) -> dict:
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LLMInvalidJSONError(f"invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LLMInvalidJSONError("LLM response is not a JSON object")
        return parsed

    def _log(self, started: float, *, success: bool, error: str | None = None) -> None:
        duration_ms = int((time.perf_counter() - started) * 1000)
        metrics_logger.info(
            "llm_call provider=%s model=%s duration_ms=%s success=%s error=%s",
            self.name,
            self.config.model,
            duration_ms,
            success,
            error or "",
        )


class LocalLLMProvider(OpenAICompatibleJSONProvider):
    pass


class ExternalOpenAICompatibleProvider(OpenAICompatibleJSONProvider):
    pass


def _build_provider(config: LLMProviderConfig) -> LLMProvider:
    if config.provider == "local":
        return LocalLLMProvider(config)
    return ExternalOpenAICompatibleProvider(config)


class LLMProviderFactory:
    def __init__(self, session_factory: async_sessionmaker, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._cipher = SecretCipher(settings.board_creds_encryption_key or "dev-key")

    async def for_team(self, team_id: UUID) -> LLMProvider:
        """Только primary (обратная совместимость)."""
        resolved = await self.resolve_for_team(team_id)
        return resolved.primary

    async def resolve_for_team(self, team_id: UUID) -> ResolvedLLM:
        primary_config = await self._resolve_primary_config(team_id)
        fallback_config = self._resolve_fallback_config()
        return ResolvedLLM(
            primary=_build_provider(primary_config),
            fallback=_build_provider(fallback_config) if fallback_config else None,
        )

    def fallback_config(self) -> LLMProviderConfig | None:
        return self._resolve_fallback_config()

    async def _resolve_primary_config(self, team_id: UUID) -> LLMProviderConfig:
        async with self._session_factory() as session:
            team = await session.get(m.TeamModel, team_id)
            if team is None:
                raise ValueError("Team not found")

            team_settings = await session.scalar(
                select(m.LLMSettingsModel).where(
                    m.LLMSettingsModel.team_id == team_id,
                    m.LLMSettingsModel.enabled.is_(True),
                )
            )
            if team_settings is not None:
                return self._from_model(team_settings)

            company_settings = await session.scalar(
                select(m.LLMSettingsModel).where(
                    m.LLMSettingsModel.company_id == team.company_id,
                    m.LLMSettingsModel.team_id.is_(None),
                    m.LLMSettingsModel.enabled.is_(True),
                )
            )
            if company_settings is not None:
                return self._from_model(company_settings)

        if self._settings.llm_enabled:
            return LLMProviderConfig(
                provider=self._settings.llm_provider,
                base_url=self._settings.effective_llm_base_url,
                model=self._settings.effective_llm_model,
                api_key=self._settings.effective_llm_api_key,
                timeout_seconds=self._settings.llm_timeout_seconds,
                max_retries=self._settings.llm_max_retries,
                strict_json=self._settings.llm_strict_json,
                proxy=self._proxy_for(self._settings.llm_provider),
            )
        raise ValueError("No LLM provider configured for team")

    def _resolve_fallback_config(self) -> LLMProviderConfig | None:
        if not self._settings.fallback_configured:
            return None
        return LLMProviderConfig(
            provider=self._settings.llm_fallback_provider,
            base_url=self._settings.llm_fallback_base_url,
            model=self._settings.llm_fallback_model,
            api_key=self._settings.llm_fallback_api_key,
            timeout_seconds=self._settings.llm_fallback_timeout_seconds,
            max_retries=self._settings.llm_max_retries,
            strict_json=self._settings.llm_strict_json,
            # Fallback uses its own proxy setting (default: direct), so it stays
            # reachable when the primary's VPN proxy is down. local → never proxied.
            proxy=self._fallback_proxy(),
        )

    def _fallback_proxy(self) -> str | None:
        if self._settings.llm_fallback_provider == "local":
            return None
        return self._settings.llm_fallback_proxy or None

    def _proxy_for(self, provider: str) -> str | None:
        """Прокси применяем только к внешним провайдерам (local/Ollama — внутри сети)."""
        if provider == "local":
            return None
        return self._settings.llm_proxy or None

    def _from_model(self, settings: m.LLMSettingsModel) -> LLMProviderConfig:
        return LLMProviderConfig(
            provider=settings.provider,
            base_url=settings.base_url,
            model=settings.model,
            api_key=self._cipher.decrypt_text(settings.api_key_encrypted) or "",
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
            strict_json=settings.strict_json,
            proxy=self._proxy_for(settings.provider),
        )
