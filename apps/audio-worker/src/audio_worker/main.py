"""Точка входа audio-worker (P0 — каркас).

Содержит:
  * GET  /health        — healthcheck;
  * POST /mock/transcript — отправить тестовое transcript-событие в brain-api;
  * CLI `python -m audio_worker.main --text "..."` — то же из консоли.

Реальный аудио-pipeline на P0 НЕ реализован.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from grey_cardinal_contracts import TranscriptEvent
from pydantic import BaseModel

from audio_worker.brain_client import BrainClient
from audio_worker.config import get_settings

logger = logging.getLogger(__name__)


class MockTranscriptRequest(BaseModel):
    text: str = "Петя, подготовь макет главного экрана до завтра 18:00"
    meeting_id: str | None = "demo-meeting"
    speaker_name: str | None = "Демо-спикер"
    is_final: bool = True


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    app = FastAPI(title="Grey Cardinal — audio-worker (skeleton)", version="0.1.0")
    brain = BrainClient(settings.brain_api_base_url, settings.internal_api_token)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "audio-worker", "mode": "skeleton"}

    @app.post("/mock/transcript")
    async def mock_transcript(payload: MockTranscriptRequest) -> dict:
        event = TranscriptEvent(
            meeting_id=payload.meeting_id,
            speaker_name=payload.speaker_name,
            text=payload.text,
            ts=datetime.now(timezone.utc),
            is_final=payload.is_final,
        )
        result = await brain.send_transcript(event)
        return {"sent": True, "brain_response": result}

    return app


app = create_app()


async def _send_cli(text: str) -> None:
    settings = get_settings()
    brain = BrainClient(settings.brain_api_base_url, settings.internal_api_token)
    event = TranscriptEvent(
        meeting_id="cli-meeting",
        speaker_name="CLI",
        text=text,
        ts=datetime.now(timezone.utc),
        is_final=True,
    )
    result = await brain.send_transcript(event)
    logger.info("brain-api ответ: %s", result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Отправить mock transcript в brain-api")
    parser.add_argument(
        "--text",
        default="Петя, подготовь макет главного экрана до завтра 18:00",
        help="Текст реплики",
    )
    args = parser.parse_args()
    asyncio.run(_send_cli(args.text))


if __name__ == "__main__":
    main()
