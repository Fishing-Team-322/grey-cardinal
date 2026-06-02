from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from brain_api import main as brain_main


TOKEN = "dev-internal-token"


def setup_function() -> None:
    brain_main.received_transcripts.clear()


def transcript_payload(text: str = "Петя, сделай оплату к четвергу") -> dict[str, object]:
    return {
        "type": "transcript",
        "meeting_id": "meeting-1",
        "speaker_id": "unknown",
        "speaker_name": None,
        "text": text,
        "ts": datetime.now(timezone.utc).isoformat(),
        "is_final": True,
        "raw": {"source": "test"},
    }


def test_health() -> None:
    response = TestClient(brain_main.app).get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_internal_audio_transcript_accepts_current_shape() -> None:
    client = TestClient(brain_main.app)

    response = client.post(
        "/internal/audio/transcript",
        json=transcript_payload(),
        headers={"X-Internal-Token": TOKEN},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "received": 1}
    assert len(brain_main.received_transcripts) == 1
    assert brain_main.received_transcripts[0].speaker_id == "unknown"


def test_internal_audio_transcript_rejects_missing_or_wrong_token() -> None:
    client = TestClient(brain_main.app)

    missing = client.post("/internal/audio/transcript", json=transcript_payload())
    wrong = client.post(
        "/internal/audio/transcript",
        json=transcript_payload(),
        headers={"X-Internal-Token": "wrong-token"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_recent_transcripts_endpoint_is_protected_and_observable() -> None:
    client = TestClient(brain_main.app)
    client.post(
        "/internal/audio/transcript",
        json=transcript_payload("mock text"),
        headers={"X-Internal-Token": TOKEN},
    )

    unauthorized = client.get("/internal/audio/transcripts/recent")
    recent = client.get(
        "/internal/audio/transcripts/recent",
        headers={"X-Internal-Token": TOKEN},
    )

    assert unauthorized.status_code == 401
    assert recent.status_code == 200
    payload = recent.json()
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["items"][0]["type"] == "transcript"
    assert payload["items"][0]["text"] == "mock text"
