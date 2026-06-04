"""YouGile integration exceptions."""

from __future__ import annotations


class YouGileError(Exception):
    """Base class for YouGile integration errors."""


class YouGileConfigError(YouGileError):
    """Raised when YouGile is used while not configured."""


class YouGileHTTPError(YouGileError):
    """Raised on a non-2xx HTTP response or a network/timeout error.

    Never carries secrets — only method, path, status and (truncated) body.
    """

    def __init__(self, method: str, path: str, status: int | None, body: str) -> None:
        self.method = method
        self.path = path
        self.status = status
        self.body = (body or "")[:500]
        code = status if status is not None else "network-error"
        super().__init__(f"YouGile {method} {path} -> {code}: {self.body}")
