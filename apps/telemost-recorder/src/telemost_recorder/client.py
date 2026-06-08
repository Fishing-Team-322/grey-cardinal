from __future__ import annotations

from typing import Any

import httpx

from .config import Settings


class RecorderClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.headers = {"X-Internal-Token": settings.internal_api_token}

    async def claim(self) -> dict[str, Any] | None:
        return await self._brain_post("/internal/meeting-agent/jobs/claim")

    async def recording(self, job_id: str) -> dict[str, Any]:
        return await self._brain_post(f"/internal/meeting-agent/jobs/{job_id}/recording")

    async def heartbeat(self, job_id: str) -> dict[str, Any]:
        return await self._brain_post(f"/internal/meeting-agent/jobs/{job_id}/heartbeat")

    async def complete(self, job_id: str) -> dict[str, Any]:
        return await self._brain_post(f"/internal/meeting-agent/jobs/{job_id}/complete")

    async def fail(self, job_id: str, message: str) -> dict[str, Any]:
        return await self._brain_post(
            f"/internal/meeting-agent/jobs/{job_id}/fail",
            {"error_message": message[:1000]},
        )

    async def upload_chunk(self, meeting_public_id: str, sequence: int, wav_bytes: bytes) -> dict:
        headers = {
            **self.headers,
            "X-Meeting-Id": meeting_public_id,
            "X-Chunk-Seq": str(sequence),
            "X-Audio-Format": "wav",
            "X-Audio-Sample-Rate": "16000",
            "X-Audio-Channels": "1",
            "X-Audio-Bits-Per-Sample": "16",
            "X-Audio-Source": "telemost_recorder",
        }
        async with httpx.AsyncClient(timeout=240.0, trust_env=False) as client:
            response = await client.post(
                f"{self.settings.audio_worker_base_url}/audio/chunk",
                headers=headers,
                content=wav_bytes,
            )
            response.raise_for_status()
            return response.json()

    async def _brain_post(self, path: str, extra: dict | None = None) -> dict | None:
        payload = {"worker_id": self.settings.worker_id, **(extra or {})}
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{self.settings.brain_api_base_url}{path}",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            if not response.content:
                return None
            return response.json()
