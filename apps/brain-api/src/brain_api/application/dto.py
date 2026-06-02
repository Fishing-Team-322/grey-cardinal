"""Внутренние DTO application-слоя.

Большинство «проводных» DTO берём напрямую из packages/contracts. Здесь только
то, что нужно внутри use cases и не является частью внешнего контракта.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from brain_api.domain.entities import Task
from brain_api.domain.enums import BoardProvider


@dataclass
class BoardCardData:
    """Результат board-адаптера, который use case сохраняет в board_cards."""

    provider: BoardProvider
    external_card_id: str
    external_url: str | None = None
    external_payload: dict | None = None


@dataclass
class ReminderTarget:
    """Что и кому напомнить (вычисляется use case'ом reminders)."""

    task: Task
    chat_id: int
    text: str


@dataclass
class DigestData:
    chat_id: int
    text: str
    generated_at: datetime
