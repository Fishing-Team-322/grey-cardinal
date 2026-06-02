from __future__ import annotations

import logging

import httpx

from grey_cardinal_contracts import TranscriptEvent

logger = logging.getLogger(__name__)


class BrainClient:
    def __init__(self, base_url: str, internal_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_token = internal_token

    async def send_transcript(self, event: TranscriptEvent) -> bool:
        url = f"{self._base_url}/internal/audio/transcript"
        headers = {"X-Internal-Token": self._internal_token}
        payload = event.model_dump(mode="json")

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("failed to send transcript to brain-api")
            return False

        return True

