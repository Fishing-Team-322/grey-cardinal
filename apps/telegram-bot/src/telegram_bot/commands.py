"""Парсинг Telegram-команд.

`/done@GreyCardinalBot GC-12` -> ("done", ["GC-12"]).
"""

from __future__ import annotations


def is_command(text: str | None) -> bool:
    return bool(text) and text.lstrip().startswith("/")


def parse_command(text: str) -> tuple[str, list[str]]:
    parts = text.strip().split()
    head = parts[0]  # /command или /command@bot
    command = head[1:]  # убрать ведущий '/'
    if "@" in command:
        command = command.split("@", 1)[0]
    args = parts[1:]
    return command.lower(), args
