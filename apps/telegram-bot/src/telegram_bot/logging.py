"""Настройка логирования telegram-bot."""

from __future__ import annotations

import logging
import re

_TELEGRAM_BOT_URL_RE = re.compile(r"(https://api\.telegram\.org/(?:file/)?bot)[^/\s]+")


def redact_telegram_token(value: str) -> str:
    return _TELEGRAM_BOT_URL_RE.sub(r"\1<redacted>", value)


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
