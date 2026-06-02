"""Клиент audio-worker -> brain-api (отправка transcript-событий)."""

from __future__ import annotations

import logging

import httpx
from grey_cardinal_contracts import TranscriptEvent

logger = logging.getLogger(__name__)


class BrainClient:
    def __init__(self, base_url: str, internal_token: str, timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = internal_token
        self._timeout = timeout

    async def send_transcript(self, event: TranscriptEvent) -> dict:
        url = f"{self._base_url}/internal/audio/transcript"
        headers = {"X-Internal-Token": self._token}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url, json=event.model_dump(mode="json"), headers=headers
            )
            response.raise_for_status()
            return response.json()
