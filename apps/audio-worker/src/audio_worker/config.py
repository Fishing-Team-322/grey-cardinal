from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    internal_api_token: str
    brain_api_base_url: str
    asr_provider: str
    mock_text: str
    save_chunks: bool
    chunks_dir: Path
    faster_whisper_model: str
    asr_service_url: str


def get_settings() -> Settings:
    return Settings(
        internal_api_token=os.getenv("INTERNAL_API_TOKEN", "dev-internal-token"),
        brain_api_base_url=os.getenv("BRAIN_API_BASE_URL", "http://localhost:8000"),
        asr_provider=os.getenv("AUDIO_ASR_PROVIDER", "mock").strip().lower(),
        mock_text=os.getenv("AUDIO_MOCK_TEXT", "Петя, сделай оплату к четвергу"),
        save_chunks=_bool_env("AUDIO_WORKER_SAVE_CHUNKS", False),
        chunks_dir=Path(os.getenv("AUDIO_WORKER_CHUNKS_DIR", "/tmp/grey-cardinal-audio-chunks")),
        faster_whisper_model=os.getenv("AUDIO_FASTER_WHISPER_MODEL", "base"),
        asr_service_url=os.getenv("ASR_SERVICE_URL", "http://asr-service:8030"),
    )
