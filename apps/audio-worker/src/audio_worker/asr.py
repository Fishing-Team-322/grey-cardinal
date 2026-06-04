from __future__ import annotations

import itertools
import tempfile
from pathlib import Path
from typing import Protocol

from .config import Settings


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


def create_asr_engine(settings: Settings) -> AsrEngine:
    if settings.asr_provider == "mock":
        return MockAsrEngine(settings.mock_text)
    if settings.asr_provider == "faster_whisper":
        return FasterWhisperAsrEngine(settings.faster_whisper_model)
    raise ValueError(f"unsupported AUDIO_ASR_PROVIDER: {settings.asr_provider}")
