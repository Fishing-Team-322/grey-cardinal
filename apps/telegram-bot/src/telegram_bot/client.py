"""Клиент Telegram Bot API (через httpx)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from telegram_bot.logging import redact_telegram_token

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, api_base: str, timeout: float = 15.0) -> None:
        self._api_base = api_base
        self._timeout = timeout

    async def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._api_base}/{method}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload)
            data = response.json()
        if not data.get("ok"):
            logger.warning("Telegram %s failed: %s", method, redact_telegram_token(str(data)))
        return data

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str | None = None,
    ) -> int | None:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        data = await self._call("sendMessage", payload)
        result = data.get("result") or {}
        return result.get("message_id")

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        await self._call("editMessageText", payload)

    async def get_file(self, file_id: str) -> dict | None:
        """Get file info from Telegram (returns file_path for download)."""
        data = await self._call("getFile", {"file_id": file_id})
        return data.get("result")

    async def download_file(self, file_path: str) -> bytes | None:
        """Download a file from Telegram servers."""
        # api_base looks like https://api.telegram.org/bot{token}
        # download url is https://api.telegram.org/file/bot{token}/{file_path}
        token_part = self._api_base.split("/bot", 1)[-1]
        url = f"https://api.telegram.org/file/bot{token_part}/{file_path}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Route through proxy if configured
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.content
                logger.warning("File download failed: %s", resp.status_code)
        except httpx.HTTPError as exc:
            logger.error("File download error: %s", redact_telegram_token(str(exc)))
        return None

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False
    ) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = True
        await self._call("answerCallbackQuery", payload)

    async def set_webhook(self, url: str, secret_token: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "url": url,
            "allowed_updates": [
                "message",
                "edited_message",
                "channel_post",
                "edited_channel_post",
                "callback_query",
                "my_chat_member",
            ],
        }
        if secret_token:
            payload["secret_token"] = secret_token
        return await self._call("setWebhook", payload)

    async def delete_webhook(self, drop_pending_updates: bool = False) -> dict[str, Any]:
        return await self._call("deleteWebhook", {"drop_pending_updates": drop_pending_updates})

    async def get_updates(
        self, offset: int | None = None, timeout: int = 25
    ) -> list[dict[str, Any]]:
        """Long-poll for updates. Uses a request timeout longer than the poll."""
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": [
                "message",
                "edited_message",
                "channel_post",
                "edited_channel_post",
                "callback_query",
                "my_chat_member",
            ],
        }
        if offset is not None:
            payload["offset"] = offset
        url = f"{self._api_base}/getUpdates"
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            response = await client.post(url, json=payload)
            data = response.json()
        if not data.get("ok"):
            logger.warning("Telegram getUpdates failed: %s", redact_telegram_token(str(data)))
            return []
        return data.get("result", [])
