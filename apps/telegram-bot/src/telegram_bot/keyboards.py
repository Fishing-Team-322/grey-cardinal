"""Клавиатуры.

На P0 telegram-bot НЕ строит inline-клавиатуры самостоятельно — `reply_markup`
приходит готовым из brain-api вместе с действием send_message/edit_message. Модуль
оставлен как точка расширения и для совместимости со структурой проекта.
"""

from __future__ import annotations

from typing import Any


def passthrough(reply_markup: dict[str, Any] | None) -> dict[str, Any] | None:
    """Вернуть клавиатуру как есть (источник — brain-api)."""
    return reply_markup
