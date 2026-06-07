"""LLM providers for v2 semantic pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain_api.config import Settings
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.security.encryption import SecretCipher


class LLMProvider(Protocol):
    async def complete_json(self, prompt: str, schema_name: str) -> dict: ...


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: int
    max_retries: int
    strict_json: bool


class OpenAICompatibleJSONProvider:
    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config

    async def complete_json(self, prompt: str, schema_name: str) -> dict:
        payload = {
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
            "response_format": {"type": "json_object"},
        }
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response is not a JSON object")
        return parsed


class LocalLLMProvider(OpenAICompatibleJSONProvider):
    pass


class ExternalOpenAICompatibleProvider(OpenAICompatibleJSONProvider):
    pass


class LLMProviderFactory:
    def __init__(self, session_factory: async_sessionmaker, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._cipher = SecretCipher(settings.board_creds_encryption_key or "dev-key")

    async def for_team(self, team_id: UUID) -> LLMProvider:
        config = await self._resolve_config(team_id)
        if config.provider == "local":
            return LocalLLMProvider(config)
        if config.provider == "external_api":
            return ExternalOpenAICompatibleProvider(config)
        raise ValueError("LLM provider is not configured")

    async def _resolve_config(self, team_id: UUID) -> LLMProviderConfig:
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
                model=self._settings.llm_model,
                api_key=self._settings.effective_llm_api_key,
                timeout_seconds=self._settings.llm_timeout_seconds,
                max_retries=self._settings.llm_max_retries,
                strict_json=self._settings.llm_strict_json,
            )
        raise ValueError("No LLM provider configured for team")

    def _from_model(self, settings: m.LLMSettingsModel) -> LLMProviderConfig:
        return LLMProviderConfig(
            provider=settings.provider,
            base_url=settings.base_url,
            model=settings.model,
            api_key=self._cipher.decrypt_text(settings.api_key_encrypted) or "",
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
            strict_json=settings.strict_json,
        )
