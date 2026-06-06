"""Базовые типы board-адаптеров.

Контракт BoardGateway определён как Protocol в application.ports. Здесь —
конфиг YouGile и фабрика, выбирающая адаптер по BOARD_PROVIDER.
"""

from __future__ import annotations

from brain_api.domain.enums import BoardProvider


def resolve_provider(value: str) -> BoardProvider:
    try:
        return BoardProvider(value)
    except ValueError:
        return BoardProvider.mock
