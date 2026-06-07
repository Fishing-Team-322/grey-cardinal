"""Типизированные ошибки LLM-провайдеров.

Категория ошибки решает, нужно ли включать fallback. Все эти ошибки —
"восстановимые" в смысле fallback: timeout / 429 / 5xx / invalid JSON /
provider unavailable. Валидный ответ ``noise``/``unknown`` ошибкой не является
и сюда не попадает.
"""

from __future__ import annotations


class LLMError(Exception):
    """Базовая ошибка провайдера. ``category`` используется для метрик/fallback."""

    category = "error"
    retryable = True


class LLMTimeoutError(LLMError):
    category = "timeout"


class LLMRateLimitError(LLMError):
    category = "rate_limit"


class LLMServerError(LLMError):
    category = "server_error"


class LLMUnavailableError(LLMError):
    category = "unavailable"


class LLMInvalidJSONError(LLMError):
    category = "invalid_json"


class LLMSchemaValidationError(LLMError):
    category = "schema_error"
