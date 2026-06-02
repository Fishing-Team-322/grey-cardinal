"""MockBoardGateway — полностью рабочий адаптер без внешних токенов.

Возвращает фейковые id/URL и логирует операции. Используется по умолчанию и
когда YouGile не настроен, чтобы P0-демо работало из коробки.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from grey_cardinal_contracts import BoardCardResult, BoardProvider

from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskStatus

logger = logging.getLogger(__name__)


class MockBoardGateway:
    def __init__(self, base_url: str = "https://mock.board.local") -> None:
        self._base_url = base_url.rstrip("/")

    async def create_card(self, task: Task) -> BoardCardResult:
        external_id = f"mock-{uuid4().hex[:12]}"
        url = f"{self._base_url}/cards/{external_id}"
        logger.info("[mock-board] create_card task=%s -> %s", task.public_id, external_id)
        return BoardCardResult(
            provider=BoardProvider.mock,
            external_card_id=external_id,
            external_url=url,
            external_payload={"title": task.title, "status": task.status.value},
        )

    async def move_card(self, external_card_id: str, status: TaskStatus) -> None:
        logger.info("[mock-board] move_card %s -> %s", external_card_id, status.value)

    async def close_card(self, external_card_id: str) -> None:
        logger.info("[mock-board] close_card %s", external_card_id)

    async def add_comment(self, external_card_id: str, text: str) -> None:
        logger.info("[mock-board] add_comment %s: %s", external_card_id, text)
