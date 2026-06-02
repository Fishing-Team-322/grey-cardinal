"""Реализация порта EventPublisher поверх WebSocketManager."""

from __future__ import annotations

import logging

from brain_api.infrastructure.events.websocket_manager import WebSocketManager
from grey_cardinal_contracts import WebsocketEvent

logger = logging.getLogger(__name__)


class WebSocketEventPublisher:
    def __init__(self, manager: WebSocketManager) -> None:
        self._manager = manager

    async def publish(self, event: WebsocketEvent) -> None:
        logger.debug("event %s -> %d ws", event.event.value, self._manager.count)
        await self._manager.broadcast(event.model_dump(mode="json"))


class NullEventPublisher:
    """Заглушка для тестов: накапливает события вместо рассылки."""

    def __init__(self) -> None:
        self.events: list[WebsocketEvent] = []

    async def publish(self, event: WebsocketEvent) -> None:
        self.events.append(event)
