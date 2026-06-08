from __future__ import annotations

import os
import socket
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    brain_api_base_url: str
    audio_worker_base_url: str
    internal_api_token: str
    worker_id: str
    participant_name: str
    poll_seconds: float
    heartbeat_seconds: float
    segment_seconds: int
    max_session_minutes: int
    join_timeout_seconds: int


def get_settings() -> Settings:
    return Settings(
        brain_api_base_url=os.getenv("BRAIN_API_BASE_URL", "http://brain-api:8000").rstrip("/"),
        audio_worker_base_url=os.getenv("AUDIO_WORKER_BASE_URL", "http://audio-worker:8020").rstrip(
            "/"
        ),
        internal_api_token=os.getenv("INTERNAL_API_TOKEN", "dev-internal-token"),
        worker_id=os.getenv("TELEMOST_RECORDER_WORKER_ID", socket.gethostname()),
        participant_name=os.getenv(
            "TELEMOST_RECORDER_PARTICIPANT_NAME", "Grey Cardinal — запись"
        ),
        poll_seconds=float(os.getenv("TELEMOST_RECORDER_POLL_SECONDS", "5")),
        heartbeat_seconds=float(os.getenv("TELEMOST_RECORDER_HEARTBEAT_SECONDS", "10")),
        segment_seconds=int(os.getenv("TELEMOST_RECORDER_SEGMENT_SECONDS", "15")),
        max_session_minutes=int(os.getenv("TELEMOST_RECORDER_MAX_SESSION_MINUTES", "180")),
        join_timeout_seconds=int(os.getenv("TELEMOST_RECORDER_JOIN_TIMEOUT_SECONDS", "60")),
    )
