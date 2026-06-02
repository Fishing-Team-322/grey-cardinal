"""Use case: вечерний дайджест (планировщик раз в день или команда /digest)."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import TelegramGateway, UnitOfWork
from brain_api.application.rendering import render_digest
from brain_api.application.use_cases.send_deadline_reminders import _default_chat_id
from brain_api.domain.entities import DigestLog
from grey_cardinal_contracts import ActionsResponse, SendMessageAction

logger = logging.getLogger(__name__)


class SendEveningDigest:
    def __init__(self, uow: UnitOfWork, telegram: TelegramGateway, config: AppConfig) -> None:
        self._uow = uow
        self._telegram = telegram
        self._config = config

    async def _build_text(self, now: datetime) -> str:
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        active = await self._uow.tasks.list_active()
        closed_today = await self._uow.tasks.count_completed_since(start_of_day)
        overdue = await self._uow.tasks.count_overdue(now)
        return render_digest(active, closed_today, overdue, self._config.timezone)

    async def _log(self, chat_id: int, text: str) -> None:
        await self._uow.digests.add(
            DigestLog(id=uuid4(), telegram_chat_id=chat_id, payload={"text": text})
        )

    async def execute(self) -> int:
        """Запуск планировщиком: отправляет дайджест в чат по умолчанию."""
        chat_id = await _default_chat_id(self._uow)
        if chat_id is None:
            return 0
        now = self._config.now()
        if await self._uow.digests.sent_today(chat_id, now):
            return 0
        text = await self._build_text(now)
        await self._telegram.send_message(chat_id, text)
        await self._log(chat_id, text)
        await self._uow.commit()
        logger.info("Evening digest sent to chat %s", chat_id)
        return 1

    async def as_actions(self, chat_id: int) -> ActionsResponse:
        """Запуск командой /digest: возвращает текст как ответ бота."""
        now = self._config.now()
        text = await self._build_text(now)
        await self._log(chat_id, text)
        await self._uow.commit()
        return ActionsResponse(actions=[SendMessageAction(chat_id=chat_id, text=text)])
