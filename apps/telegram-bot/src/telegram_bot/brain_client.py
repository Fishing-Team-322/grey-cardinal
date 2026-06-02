"""Клиент telegram-bot -> brain-api.

Отправляет нормализованные события на internal-эндпоинты brain-api и возвращает
список действий (ActionsResponse). Все запросы защищены X-Internal-Token.
"""

from __future__ import annotations

import logging

import httpx

from grey_cardinal_contracts import (
    ActionsResponse,
    TelegramCallbackEvent,
    TelegramCommandEvent,
    TelegramMessageEvent,
)

logger = logging.getLogger(__name__)


class BrainClient:
    def __init__(self, base_url: str, internal_token: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = internal_token
        self._timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Token": self._token}

    async def _post(self, path: str, payload: dict) -> ActionsResponse:
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=self._headers)
                response.raise_for_status()
                return ActionsResponse.model_validate(response.json())
        except httpx.HTTPError as exc:
            logger.error("brain-api %s failed: %s", path, exc)
            return ActionsResponse(actions=[])

    async def send_message_event(self, event: TelegramMessageEvent) -> ActionsResponse:
        return await self._post("/internal/telegram/message", event.model_dump(mode="json"))

    async def send_command_event(self, event: TelegramCommandEvent) -> ActionsResponse:
        return await self._post("/internal/telegram/command", event.model_dump(mode="json"))

    async def send_callback_event(self, event: TelegramCallbackEvent) -> ActionsResponse:
        return await self._post("/internal/telegram/callback", event.model_dump(mode="json"))
