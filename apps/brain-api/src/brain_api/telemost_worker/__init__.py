"""Telemost bot worker package.

Exports factory function get_worker() that returns the active worker
based on TELEMOST_WORKER_MODE environment variable.

Default: mock (no browser required).
"""

from brain_api.telemost_worker.base import BotSessionData, TelemostBotWorker
from brain_api.telemost_worker.factory import get_worker

__all__ = ["TelemostBotWorker", "BotSessionData", "get_worker"]
