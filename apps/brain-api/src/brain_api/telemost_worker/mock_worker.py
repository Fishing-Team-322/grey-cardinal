"""Mock Telemost bot worker.

Demo implementation: manages session state only.
Does NOT open a browser, does NOT join a real meeting,
does NOT record audio, does NOT create fake transcriptions or tasks.

This is the default worker (TELEMOST_WORKER_MODE=mock).
Real browser joiner can replace this by implementing TelemostBotWorker
and registering it in factory.py.

How real worker would plug in:
    1. Override start_session() to launch Playwright Chromium.
    2. Navigate to meeting_url.
    3. Handle "Continue in browser" prompt.
    4. Set participant name to TELEMOST_BOT_NAME.
    5. Mute camera, grant mic permissions.
    6. Start recording tab/system audio.
    7. On stop_session() — finalize WAV, POST /api/audio/upload with source=telemost_bot.
    8. Update session status through the states: joining→joined→recording→uploading→uploaded.
"""

from __future__ import annotations

import logging

from brain_api.telemost_worker.base import BotSessionData, TelemostBotWorker

logger = logging.getLogger(__name__)


class MockTelemostBotWorker(TelemostBotWorker):
    """Demo worker: records session state, no real browser or audio capture."""

    async def start_session(self, session: BotSessionData) -> None:
        """Mark session as joining. In real worker: launch browser here."""
        session.status = "joining"
        logger.info(
            "[mock] Telemost bot session started: bot_session_id=%s meeting_id=%s url=%s",
            session.bot_session_id,
            session.meeting_id,
            session.meeting_url,
        )
        # Hook point: replace with real Playwright join logic.
        # Example:
        #   async with async_playwright() as p:
        #       browser = await p.chromium.launch()
        #       page = await browser.new_page()
        #       await page.goto(session.meeting_url)
        #       await page.click("text=Continue in browser")
        #       ...

    async def stop_session(self, bot_session_id: str) -> None:
        """Mark session as left. In real worker: stop recording and upload here."""
        logger.info(
            "[mock] Telemost bot session stopped: bot_session_id=%s",
            bot_session_id,
        )
        # Hook point: finalize WAV and POST /api/audio/upload here.
        # Example:
        #   wav_path = recorder.stop()
        #   upload_audio(wav_path, meeting_id=session.meeting_id, source="telemost_bot")
