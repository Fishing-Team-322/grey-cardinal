from __future__ import annotations

import io
import wave
from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from audio_worker import main as audio_main
from grey_cardinal_contracts import (
    MeetingStatus,
    MeetingStatusResponse,
    TranscriptIngestResponse,
)

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


def tiny_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16)
    return buffer.getvalue()


class FakeBrainClient:
    def __init__(self) -> None:
        self.events = []

    async def send_transcript(self, event):
        self.events.append(event)
        return TranscriptIngestResponse(transcript_id="transcript-id")

    async def start_meeting(self, request):
        return MeetingStatusResponse(
            public_id="MTG-1",
            status=MeetingStatus.active,
            started_at=NOW,
        )

    async def stop_meeting(self, meeting_public_id, request):
        return MeetingStatusResponse(
            public_id=meeting_public_id,
            status=MeetingStatus.stopped,
            started_at=NOW,
            stopped_at=NOW,
        )


class FixedAsrEngine:
    async def transcribe_wav(self, wav_bytes: bytes) -> str:
        return "mock transcript text"


def install_fakes(monkeypatch, tmp_path=None):
    fake_brain = FakeBrainClient()
    monkeypatch.setattr(audio_main, "brain_client", fake_brain)
    monkeypatch.setattr(audio_main, "asr_engine", FixedAsrEngine())

    settings = replace(
        audio_main.settings,
        internal_api_token="test-token",
        mock_text="mock transcript text",
        save_chunks=tmp_path is not None,
        chunks_dir=tmp_path or audio_main.settings.chunks_dir,
    )
    monkeypatch.setattr(audio_main, "settings", settings)
    return fake_brain


def test_health(monkeypatch):
    install_fakes(monkeypatch)

    response = TestClient(audio_main.app).get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_legacy_session_current_is_not_exposed(monkeypatch):
    install_fakes(monkeypatch)

    response = TestClient(audio_main.app).get("/session/current")

    assert response.status_code == 404


def test_audio_chunk_accepts_tiny_wav_and_sends_transcript(monkeypatch):
    fake_brain = install_fakes(monkeypatch)
    client = TestClient(audio_main.app)

    response = client.post(
        "/audio/chunk",
        content=tiny_wav(),
        headers={
            "X-Internal-Token": "test-token",
            "X-Meeting-Id": "meeting-1",
            "X-Chunk-Seq": "3",
            "X-Audio-Format": "wav",
        },
    )

    assert response.status_code == 200
    assert response.json()["sent_to_brain"] is True
    assert len(fake_brain.events) == 1
    event = fake_brain.events[0]
    assert event.type == "transcript"
    assert event.speaker_id == "unknown"
    assert event.speaker_name is None
    assert event.text == "mock transcript text"
    assert event.meeting_id == "meeting-1"
    assert event.is_final is True
    assert event.raw["chunk_seq"] == 3


def test_audio_chunk_rejects_missing_or_wrong_token(monkeypatch):
    install_fakes(monkeypatch)
    client = TestClient(audio_main.app)

    missing = client.post("/audio/chunk", content=tiny_wav())
    wrong = client.post(
        "/audio/chunk",
        content=tiny_wav(),
        headers={"X-Internal-Token": "wrong-token"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_audio_chunk_rejects_empty_or_non_wav_payload(monkeypatch):
    install_fakes(monkeypatch)
    client = TestClient(audio_main.app)
    headers = {"X-Internal-Token": "test-token", "X-Audio-Format": "wav"}

    empty = client.post("/audio/chunk", content=b"", headers=headers)
    non_wav = client.post("/audio/chunk", content=b"not a wav", headers=headers)

    assert empty.status_code == 400
    assert empty.json()["detail"] == "empty audio chunk"
    assert non_wav.status_code == 400
    assert non_wav.json()["detail"] == "invalid WAV payload"


def test_audio_chunk_saves_wav_when_enabled(monkeypatch, tmp_path):
    install_fakes(monkeypatch, tmp_path)
    client = TestClient(audio_main.app)

    response = client.post(
        "/audio/chunk",
        content=tiny_wav(),
        headers={
            "X-Internal-Token": "test-token",
            "X-Meeting-Id": "meeting/save",
            "X-Chunk-Seq": "9",
            "X-Audio-Format": "wav",
        },
    )

    assert response.status_code == 200
    saved = tmp_path / "meeting_save" / "chunk-000009.wav"
    assert saved.exists()
    assert saved.read_bytes()[0:4] == b"RIFF"


def test_mock_transcript_sends_event(monkeypatch):
    fake_brain = install_fakes(monkeypatch)
    response = TestClient(audio_main.app).post(
        "/mock/transcript",
        json={"text": "Петя, подготовь оплату", "meeting_id": "MTG-1"},
        headers={"X-Internal-Token": "test-token"},
    )

    assert response.status_code == 200
    assert response.json()["sent_to_brain"] is True
    assert fake_brain.events[-1].meeting_id == "MTG-1"


def test_mock_meeting_and_scenario(monkeypatch):
    fake_brain = install_fakes(monkeypatch)
    client = TestClient(audio_main.app)
    headers = {"X-Internal-Token": "test-token"}

    started = client.post("/mock/meeting/start", json={}, headers=headers)
    scenario = client.post("/mock/scenario", json={"meeting_id": "MTG-1"}, headers=headers)
    stopped = client.post("/mock/meeting/stop", json={"meeting_id": "MTG-1"}, headers=headers)

    assert started.json()["meeting"]["public_id"] == "MTG-1"
    assert scenario.json()["sent"] == 3
    assert len(fake_brain.events) == 3
    assert stopped.json()["meeting"]["status"] == "stopped"
