"""YouGile integration exceptions.

Never carry secrets — only method, path, status and a truncated body.
"""

from __future__ import annotations


class YouGileError(Exception):
    """Base class for YouGile integration errors."""


class YouGileConfigError(YouGileError):
    """Raised when the client is used without an API key."""


class YouGileHTTPError(YouGileError):
    """A non-2xx HTTP response that isn't mapped to a more specific error."""

    def __init__(self, method: str, path: str, status: int | None, body: str) -> None:
        self.method = method
        self.path = path
        self.status = status
        self.body = (body or "")[:500]
        code = status if status is not None else "network-error"
        super().__init__(f"YouGile {method} {path} -> {code}: {self.body}")


class YouGileAuthError(YouGileHTTPError):
    """401 — API key invalid or expired (team should be reconnected)."""


class YouGilePermissionError(YouGileHTTPError):
    """403 — key is valid but lacks permission for the resource."""


class YouGileNotFound(YouGileHTTPError):
    """404 — resource not found."""


class YouGileServerError(YouGileHTTPError):
    """5xx (after retries) or a network/timeout error."""
