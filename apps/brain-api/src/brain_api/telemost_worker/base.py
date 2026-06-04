"""Abstract interface for Telemost bot worker.

Any concrete worker (mock, playwright, etc.) must implement TelemostBotWorker.
The worker is responsible only for joining/leaving the meeting and uploading audio.
It must NOT produce transcriptions or tasks — audio goes through the common
POST /api/audio/upload pipeline.

Bot session lifecycle:
    created → joining → joined → recording → uploading → uploaded → left | error
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

BotStatus = Literal[
    "created",
    "joining",
    "joined",
    "recording",
    "uploading",
    "uploaded",
    "left",
    "error",
]


@dataclass
class BotSessionData:
    bot_session_id: str
    meeting_id: str
    meeting_url: str
    status: BotStatus = "created"
    error_message: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )


class TelemostBotWorker(abc.ABC):
    """Abstract Telemost bot worker.

    Concrete implementations:
    - MockTelemostBotWorker  — demo/session manager (no browser)
    - PlaywrightTelemostBotWorker — real browser automation (not enabled by default)
    """

    @abc.abstractmethod
    async def start_session(self, session: BotSessionData) -> None:
        """Called after bot session is created.

        Should update session.status to "joining" and trigger async join logic.
        Must NOT block the HTTP response — use background tasks or fire-and-forget.
        Must NOT produce fake transcriptions or tasks.
        """

    @abc.abstractmethod
    async def stop_session(self, bot_session_id: str) -> None:
        """Called when frontend requests leave.

        Should set session status to "left" and stop any recording.
        """
