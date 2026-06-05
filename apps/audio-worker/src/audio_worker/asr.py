from __future__ import annotations

import itertools
import logging
import tempfile
from pathlib import Path
from typing import Protocol

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class AsrEngine(Protocol):
    async def transcribe_wav(self, wav_bytes: bytes) -> str: ...


class MockAsrEngine:
    def __init__(self, configured_text: str) -> None:
        self._configured_text = configured_text
        self._phrases = [
            configured_text,
            "Созвон записан, задача уйдет в Grey Cardinal.",
            "Follow up after the meeting and confirm the payment deadline.",
        ]
        self._counter = itertools.count()

    async def transcribe_wav(self, wav_bytes: bytes) -> str:
        index = next(self._counter) % len(self._phrases)
        return self._phrases[index]


class FasterWhisperAsrEngine:
    def __init__(self, model_name: str) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "AUDIO_ASR_PROVIDER=faster_whisper requires the optional faster-whisper package"
            ) from exc

        self._model = WhisperModel(model_name, device="cpu", compute_type="int8")

    async def transcribe_wav(self, wav_bytes: bytes) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            handle.write(wav_bytes)
            temp_path = Path(handle.name)

        try:
            segments, _info = self._model.transcribe(str(temp_path))
            return " ".join(segment.text.strip() for segment in segments).strip()
        finally:
            temp_path.unlink(missing_ok=True)


class HttpAsrEngine:
    """Delegates transcription to a remote asr-service via HTTP (e.g. asr-service:8030)."""

    def __init__(self, url: str) -> None:
        self._url = url.rstrip("/") + "/transcribe"

    async def transcribe_wav(self, wav_bytes: bytes) -> str:
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    self._url,
                    content=wav_bytes,
                    headers={"Content-Type": "audio/wav"},
                )
                resp.raise_for_status()
                return (resp.json().get("text") or "").strip()
        except Exception:
            logger.exception("HTTP ASR call to %s failed", self._url)
            return ""


def create_asr_engine(settings: Settings) -> AsrEngine:
    if settings.asr_provider == "mock":
        return MockAsrEngine(settings.mock_text)
    if settings.asr_provider == "faster_whisper":
        return FasterWhisperAsrEngine(settings.faster_whisper_model)
    if settings.asr_provider == "http":
        return HttpAsrEngine(settings.asr_service_url)
    raise ValueError(f"unsupported AUDIO_ASR_PROVIDER: {settings.asr_provider}")
