from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .audio import AudioSegmenter
from .browser import TelemostBrowser
from .client import RecorderClient
from .config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
settings = get_settings()
client = RecorderClient(settings)


async def upload_ready(segmenter: AudioSegmenter, meeting_id: str, sequence: int) -> int:
    for path in segmenter.ready_chunks():
        await client.upload_chunk(meeting_id, sequence, path.read_bytes())
        segmenter.mark_uploaded(path)
        sequence += 1
    return sequence


async def run_job(job: dict) -> None:
    job_id = job["id"]
    meeting_id = job["meeting_public_id"]
    directory = Path("/tmp/telemost-recordings") / job_id
    shutil.rmtree(directory, ignore_errors=True)
    browser = TelemostBrowser(settings.participant_name, settings.join_timeout_seconds)
    segmenter = AudioSegmenter(directory, settings.segment_seconds)
    sequence = 0
    try:
        await browser.join(job["meeting_url"])
        await segmenter.start()
        await client.recording(job_id)
        deadline = datetime.now(UTC) + timedelta(minutes=settings.max_session_minutes)
        next_heartbeat = datetime.now(UTC)
        while datetime.now(UTC) < deadline:
            if datetime.now(UTC) >= next_heartbeat:
                state = await client.heartbeat(job_id)
                if state.get("stop_requested"):
                    break
                next_heartbeat = datetime.now(UTC) + timedelta(seconds=settings.heartbeat_seconds)
            if await browser.meeting_ended():
                break
            sequence = await upload_ready(segmenter, meeting_id, sequence)
            await asyncio.sleep(1)

        await segmenter.stop()
        for path in segmenter.ready_chunks(include_latest=True):
            await client.upload_chunk(meeting_id, sequence, path.read_bytes())
            segmenter.mark_uploaded(path)
            sequence += 1
        await client.complete(job_id)
        logger.info("Completed recording job %s with %d chunks", job_id, sequence)
    except Exception as exc:
        logger.exception("Recording job %s failed", job_id)
        try:
            await client.fail(job_id, f"{type(exc).__name__}: {exc}")
        except Exception:
            logger.exception("Could not mark recording job %s failed", job_id)
    finally:
        await segmenter.stop()
        await browser.close()
        shutil.rmtree(directory, ignore_errors=True)


async def main() -> None:
    logger.info("Telemost recorder worker %s started", settings.worker_id)
    while True:
        try:
            job = await client.claim()
            if job:
                await run_job(job)
            else:
                await asyncio.sleep(settings.poll_seconds)
        except Exception:
            logger.exception("Recorder polling failed")
            await asyncio.sleep(settings.poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())
