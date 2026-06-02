"""HTTP-клиент brain-api -> telegram-bot.

Реализует порт TelegramGateway, вызывая внутренний endpoint бота
POST /internal/send-message с заголовком X-Internal-Token.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class HttpTelegramGateway:
    def __init__(self, bot_base_url: str, internal_token: str, timeout: float = 15.0) -> None:
        self._base_url = bot_base_url.rstrip("/")
        self._token = internal_token
        self._timeout = timeout

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> int | None:
        payload = {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        headers = {"X-Internal-Token": self._token}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/internal/send-message", json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()
            return data.get("message_id")
        except httpx.HTTPError as exc:
            logger.warning("telegram-bot send-message failed: %s", exc)
            return None


class NullTelegramGateway:
    """Заглушка для тестов/окружений без telegram-bot."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> int | None:
        self.sent.append((chat_id, text))
        logger.info("[null-telegram] -> chat %s: %s", chat_id, text.splitlines()[0])
        return None
