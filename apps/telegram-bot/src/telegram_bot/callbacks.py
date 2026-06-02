"""Помощники для callback-данных.

Бизнес-смысл callback'ов живёт в brain-api; здесь — только лёгкая проверка
формата `action:uuid`, чтобы заранее отсеять мусор при желании.
"""

from __future__ import annotations

KNOWN_ACTIONS = {"confirm_task", "reject_task", "edit_task"}


def split_callback(data: str) -> tuple[str, str | None]:
    if ":" not in data:
        return data, None
    action, _, payload = data.partition(":")
    return action, payload or None
