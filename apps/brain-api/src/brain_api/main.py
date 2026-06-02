from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException

from grey_cardinal_contracts import TranscriptEvent

from .config import get_settings

app = FastAPI(title="Grey Cardinal Brain API")
settings = get_settings()
received_transcripts: list[TranscriptEvent] = []


@app.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "brain-api", "transcripts": len(received_transcripts)}


@app.post("/internal/audio/transcript")
async def receive_transcript(
    event: TranscriptEvent,
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
) -> dict[str, object]:
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=401, detail="invalid internal token")

    received_transcripts.append(event)
    return {"ok": True, "received": len(received_transcripts)}

