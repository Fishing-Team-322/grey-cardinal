from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException

from grey_cardinal_contracts import TranscriptEvent

from .config import get_settings

app = FastAPI(title="Grey Cardinal Brain API")
settings = get_settings()
received_transcripts: list[TranscriptEvent] = []


def _validate_internal_token(value: str) -> None:
    if value != settings.internal_api_token:
        raise HTTPException(status_code=401, detail="invalid internal token")


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "brain-api", "transcripts": len(received_transcripts)}


@app.post("/internal/audio/transcript")
async def receive_transcript(
    event: TranscriptEvent,
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
) -> dict[str, object]:
    _validate_internal_token(x_internal_token)

    received_transcripts.append(event)
    return {"ok": True, "received": len(received_transcripts)}


@app.get("/internal/audio/transcripts/recent")
async def recent_transcripts(
    limit: int = 20,
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
) -> dict[str, object]:
    """Internal/dev-only endpoint for local audio pipeline validation."""
    _validate_internal_token(x_internal_token)
    safe_limit = max(1, min(limit, 100))
    items = received_transcripts[-safe_limit:]
    return {
        "ok": True,
        "count": len(items),
        "items": [event.model_dump(mode="json") for event in items],
    }
