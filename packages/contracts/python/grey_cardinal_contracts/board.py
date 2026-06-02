"""Контракты board-адаптеров (внешние канбан-доски)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BoardProvider(str, Enum):
    yougile = "yougile"
    mock = "mock"


class BoardCardResult(BaseModel):
    """Результат создания карточки во внешней доске."""

    provider: BoardProvider
    external_card_id: str
    external_url: str | None = None
    external_payload: dict[str, Any] = Field(default_factory=dict)
