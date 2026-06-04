"""Worker factory — selects implementation based on TELEMOST_WORKER_MODE env var.

TELEMOST_WORKER_MODE=mock        → MockTelemostBotWorker (default, no browser)
TELEMOST_WORKER_MODE=playwright  → PlaywrightTelemostBotWorker (requires playwright)

If playwright is not installed and mode=playwright, falls back to mock with a warning.
"""

from __future__ import annotations

import logging
import os

from brain_api.telemost_worker.base import TelemostBotWorker

logger = logging.getLogger(__name__)

_worker_instance: TelemostBotWorker | None = None


def get_worker() -> TelemostBotWorker:
    """Return the singleton worker instance.

    Reads TELEMOST_WORKER_MODE on first call and caches the instance.
    Override with set_worker() in tests.
    """
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = _create_worker()
    return _worker_instance


def set_worker(worker: TelemostBotWorker) -> None:
    """Replace worker — used in tests."""
    global _worker_instance
    _worker_instance = worker


def reset_worker() -> None:
    """Reset cached worker — used in tests."""
    global _worker_instance
    _worker_instance = None


def _create_worker() -> TelemostBotWorker:
    mode = os.getenv("TELEMOST_WORKER_MODE", "mock").lower()

    if mode == "playwright":
        return _try_playwright_worker()

    # Default: mock
    from brain_api.telemost_worker.mock_worker import MockTelemostBotWorker

    logger.info("[telemost] Using mock worker (TELEMOST_WORKER_MODE=mock)")
    return MockTelemostBotWorker()


def _try_playwright_worker() -> TelemostBotWorker:
    """Try to load Playwright worker. Falls back to mock if not available."""
    try:
        from brain_api.telemost_worker.playwright_worker import (
            PlaywrightTelemostBotWorker,  # type: ignore[import]
        )

        logger.info("[telemost] Using Playwright worker (TELEMOST_WORKER_MODE=playwright)")
        return PlaywrightTelemostBotWorker()
    except ImportError:
        logger.warning(
            "[telemost] playwright not installed — falling back to mock worker. "
            "Install with: pip install 'brain-api[telemost]'"
        )
        from brain_api.telemost_worker.mock_worker import MockTelemostBotWorker

        return MockTelemostBotWorker()
