"""Настройка логирования telegram-bot."""

from __future__ import annotations

import logging
import re
from typing import Any

_TELEGRAM_BOT_URL_RE = re.compile(r"(https://api\.telegram\.org/(?:file/)?bot)[^/\s]+")


def redact_telegram_token(value: str) -> str:
    return _TELEGRAM_BOT_URL_RE.sub(r"\1<redacted>", value)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    text = str(value)
    redacted = redact_telegram_token(text)
    return redacted if redacted != text else value


class TelegramTokenRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_value(record.msg)
        record.args = _redact_value(record.args)
        return True


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(item, TelegramTokenRedactionFilter) for item in handler.filters):
            handler.addFilter(TelegramTokenRedactionFilter())

    # Successful polling requests are noisy and include the token-bearing URL.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
