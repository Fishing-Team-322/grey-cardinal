"""Точка входа telegram-bot (FastAPI)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, status

from grey_cardinal_contracts import (
    AnswerCallbackRequest,
    EditMessageRequest,
    SendMessageRequest,
    SendMessageResponse,
)
from telegram_bot.brain_client import BrainClient
from telegram_bot.client import TelegramClient
from telegram_bot.config import Settings, get_settings
from telegram_bot.logging import setup_logging
from telegram_bot.webhook import process_update

logger = logging.getLogger(__name__)


async def _poll_loop(app: FastAPI) -> None:
    """Long-polling worker: pull updates from Telegram and dispatch them.

    Used when Telegram cannot deliver webhooks to this host. Outbound Telegram
    traffic goes through the configured HTTPS proxy (tg-proxy).
    """
    settings: Settings = app.state.settings
    client: TelegramClient = app.state.client
    brain: BrainClient = app.state.brain
    # getUpdates and a webhook are mutually exclusive — drop any webhook first.
    try:
        await client.delete_webhook(drop_pending_updates=False)
    except Exception:
        logger.exception("deleteWebhook before polling failed")
    offset: int | None = None
    logger.info("telegram-bot long-polling started")
    while True:
        try:
            updates = await client.get_updates(
                offset=offset, timeout=settings.telegram_poll_timeout
            )
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    await process_update(update, client, brain)
                except Exception:
                    logger.exception("process_update failed")
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("getUpdates loop error")
            await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    app.state.settings = settings
    app.state.client = TelegramClient(settings.telegram_api_base)
    app.state.brain = BrainClient(settings.brain_api_base_url, settings.internal_api_token)
    logger.info("telegram-bot started (env=%s)", settings.app_env)

    poll_task: asyncio.Task | None = None
    if settings.telegram_use_polling and settings.telegram_bot_token:
        poll_task = asyncio.create_task(_poll_loop(app))

    yield

    if poll_task is not None:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task
    logger.info("telegram-bot stopped")


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _verify_internal(request: Request, token: str | None) -> None:
    expected = request.app.state.settings.internal_api_token
    if not token or token != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid X-Internal-Token")


def create_app() -> FastAPI:
    app = FastAPI(title="Grey Cardinal — telegram-bot", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "telegram-bot"}

    @app.post("/webhooks/telegram")
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        settings = _settings(request)
        # Проверка секрета вебхука (если задан).
        if (
            settings.telegram_webhook_secret
            and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bad webhook secret")
        update = await request.json()
        await process_update(update, request.app.state.client, request.app.state.brain)
        return {"ok": True}

    @app.post("/internal/send-message", response_model=SendMessageResponse)
    async def internal_send_message(
        payload: SendMessageRequest,
        request: Request,
        x_internal_token: str | None = Header(default=None),
    ) -> SendMessageResponse:
        _verify_internal(request, x_internal_token)
        message_id = await request.app.state.client.send_message(
            payload.chat_id, payload.text, payload.reply_markup
        )
        return SendMessageResponse(ok=message_id is not None, message_id=message_id)

    @app.post("/internal/edit-message")
    async def internal_edit_message(
        payload: EditMessageRequest,
        request: Request,
        x_internal_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        _verify_internal(request, x_internal_token)
        await request.app.state.client.edit_message_text(
            payload.chat_id, payload.message_id, payload.text, payload.reply_markup
        )
        return {"ok": True}

    @app.post("/internal/answer-callback")
    async def internal_answer_callback(
        payload: AnswerCallbackRequest,
        request: Request,
        x_internal_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        _verify_internal(request, x_internal_token)
        await request.app.state.client.answer_callback_query(
            payload.callback_query_id, payload.text, payload.show_alert
        )
        return {"ok": True}

    return app


app = create_app()
