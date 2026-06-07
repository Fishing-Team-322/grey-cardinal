"""Утилиты для безопасного логирования LLM-вызовов.

Никогда не логируем API-ключи и заголовок ``Authorization``. Эти хелперы
используются и в провайдерах, и в health/eval, чтобы один раз решить, как
маскировать секреты.
"""

from __future__ import annotations

from collections.abc import Mapping

_SENSITIVE_HEADERS = {"authorization", "x-api-key", "api-key", "proxy-authorization"}
_MASK = "***redacted***"


def redact_secret(value: str | None) -> str:
    """Замаскировать секрет, оставив только короткий хвост для отладки.

    >>> redact_secret("gsk_abcdef0123456789")
    'gsk_***6789'
    """
    if not value:
        return ""
    cleaned = value.strip()
    if len(cleaned) <= 8:
        return _MASK
    return f"{cleaned[:4]}***{cleaned[-4:]}"


def redact_authorization_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Вернуть копию заголовков с замаскированными чувствительными значениями."""
    if not headers:
        return {}
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADERS:
            redacted[key] = _MASK
        else:
            redacted[key] = value
    return redacted
