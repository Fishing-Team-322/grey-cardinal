from __future__ import annotations

import logging

import httpx

from grey_cardinal_contracts import (
    MeetingStartRequest,
    MeetingStatusResponse,
    MeetingStopRequest,
    TranscriptEvent,
    TranscriptIngestResponse,
)



logger = logging.getLogger(__name__)


class BrainClient:
    def __init__(self, base_url: str, internal_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_token = internal_token

    async def send_transcript(self, event: TranscriptEvent) -> TranscriptIngestResponse | None:
        data = await self._post("/internal/audio/transcript", event.model_dump(mode="json"))
        return TranscriptIngestResponse.model_validate(data) if data else None

    async def start_meeting(self, request: MeetingStartRequest) -> MeetingStatusResponse | None:
        data = await self._post("/internal/meetings/start", request.model_dump(mode="json"))
        return MeetingStatusResponse.model_validate(data) if data else None

    async def stop_meeting(
        self, meeting_public_id: str, request: MeetingStopRequest
    ) -> MeetingStatusResponse | None:
        data = await self._post(
            f"/internal/meetings/{meeting_public_id}/stop",
            request.model_dump(mode="json"),
        )
        return MeetingStatusResponse.model_validate(data) if data else None

    async def get_active_meeting(self) -> MeetingStatusResponse | None:
        """Return the currently active workspace meeting, or None if none is running."""
        url = f"{self._base_url}/internal/meetings/active"
        headers = {"X-Internal-Token": self._internal_token}
        try:
            async with httpx.AsyncClient(timeout=4.0, trust_env=False) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return MeetingStatusResponse.model_validate(data) if data else None
        except httpx.HTTPError:
            logger.debug("get_active_meeting failed")
        return None

    async def _post(self, path: str, payload: dict) -> dict | None:
        url = f"{self._base_url}{path}"
        headers = {"X-Internal-Token": self._internal_token}

        try:
            async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("brain-api POST %s failed", path)
            return None

        return response.json()
