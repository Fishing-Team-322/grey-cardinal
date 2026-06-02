from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException, Request

from grey_cardinal_contracts import (
    DemoScenarioPayload,
    MeetingStartRequest,
    MeetingStopRequest,
    TranscriptEvent,
    TranscriptSource,
)

from .asr import create_asr_engine
from .brain_client import BrainClient
from .config import get_settings

app = FastAPI(title="Grey Cardinal Audio Worker")
settings = get_settings()
brain_client = BrainClient(settings.brain_api_base_url, settings.internal_api_token)
asr_engine = create_asr_engine(settings)


def _validate_internal_token(value: str) -> None:
    if value != settings.internal_api_token:
        raise HTTPException(status_code=401, detail="invalid internal token")


def _validate_wav_payload(wav_bytes: bytes, audio_format: str) -> None:
    if audio_format.strip().lower() != "wav":
        raise HTTPException(status_code=415, detail="unsupported audio format")
    if len(wav_bytes) < 44 or wav_bytes[0:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        raise HTTPException(status_code=400, detail="invalid WAV payload")


def _save_chunk(wav_bytes: bytes, meeting_id: str, chunk_seq: int) -> str | None:
    if not settings.save_chunks:
        return None

    safe_meeting_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in meeting_id)
    directory: Path = settings.chunks_dir / safe_meeting_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"chunk-{chunk_seq:06d}.wav"
    path.write_bytes(wav_bytes)
    return str(path)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "service": "audio-worker",
        "asr_provider": settings.asr_provider,
        "save_chunks": settings.save_chunks,
    }


@app.post("/mock/transcript")
async def mock_transcript(
    payload: dict[str, Any] | None = Body(default=None),
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
) -> dict[str, object]:
    _validate_internal_token(x_internal_token)
    payload = payload or {}
    text = str(payload.get("text") or settings.mock_text)
    meeting_id = payload.get("meeting_id") or "mock-demo"

    event = TranscriptEvent(
        meeting_id=meeting_id,
        speaker_id="unknown",
        speaker_name=payload.get("speaker_name"),
        text=text,
        ts=datetime.now(UTC),
        is_final=True,
        raw={"source": "audio-worker.mock"},
    )
    result = await brain_client.send_transcript(event)
    return {
        "ok": result is not None,
        "meeting_id": meeting_id,
        "text": text,
        "sent_to_brain": result is not None,
        "brain_response": result.model_dump(mode="json") if result else None,
    }


@app.post("/mock/meeting/start")
async def mock_meeting_start(
    payload: dict[str, Any] | None = Body(default=None),
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
) -> dict[str, object]:
    _validate_internal_token(x_internal_token)
    payload = payload or {}
    result = await brain_client.start_meeting(
        MeetingStartRequest(
            telegram_chat_id=payload.get("telegram_chat_id"),
            external_source="audio_worker",
            title=payload.get("title"),
            metadata=payload.get("metadata") or {},
        )
    )
    return {"ok": result is not None, "meeting": result.model_dump(mode="json") if result else None}


@app.post("/mock/meeting/stop")
async def mock_meeting_stop(
    payload: dict[str, Any] = Body(),
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
) -> dict[str, object]:
    _validate_internal_token(x_internal_token)
    meeting_id = str(payload.get("meeting_id") or "")
    if not meeting_id:
        raise HTTPException(status_code=422, detail="meeting_id is required")
    result = await brain_client.stop_meeting(
        meeting_id, MeetingStopRequest(telegram_chat_id=payload.get("telegram_chat_id"))
    )
    return {"ok": result is not None, "meeting": result.model_dump(mode="json") if result else None}


@app.post("/mock/scenario")
async def mock_scenario(
    payload: DemoScenarioPayload = Body(default_factory=DemoScenarioPayload),
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
) -> dict[str, object]:
    _validate_internal_token(x_internal_token)
    meeting_id = payload.meeting_id
    if meeting_id is None:
        meeting = await brain_client.start_meeting(
            MeetingStartRequest(external_source="demo", metadata={"demo": True})
        )
        if meeting is None:
            return {"ok": False, "sent": 0, "meeting_id": None}
        meeting_id = meeting.public_id

    lines = [
        ("Петя", "Петя, подготовь оплату к четвергу"),
        ("Аня", "Аня, проверь интеграцию с YouGile сегодня вечером"),
        ("Дима", "Дима, подними websocket для дашборда до завтра"),
    ]
    sent = 0
    for speaker, text in lines:
        result = await brain_client.send_transcript(
            TranscriptEvent(
                meeting_id=meeting_id,
                speaker_name=speaker,
                text=text,
                ts=datetime.now(UTC),
                source=TranscriptSource.demo,
            )
        )
        sent += int(result is not None)
        if payload.delay_seconds:
            await asyncio.sleep(payload.delay_seconds)
    return {"ok": sent == len(lines), "sent": sent, "meeting_id": meeting_id}


@app.post("/audio/chunk")
async def receive_audio_chunk(
    request: Request,
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
    x_meeting_id: str = Header(default="local-windows-demo", alias="X-Meeting-Id"),
    x_chunk_seq: int = Header(default=0, alias="X-Chunk-Seq"),
    x_audio_format: str = Header(default="wav", alias="X-Audio-Format"),
) -> dict[str, object]:
    _validate_internal_token(x_internal_token)

    wav_bytes = await request.body()
    if not wav_bytes:
        raise HTTPException(status_code=400, detail="empty audio chunk")
    _validate_wav_payload(wav_bytes, x_audio_format)

    saved_path = _save_chunk(wav_bytes, x_meeting_id, x_chunk_seq)
    text = await asr_engine.transcribe_wav(wav_bytes)

    event = TranscriptEvent(
        meeting_id=x_meeting_id,
        speaker_id="unknown",
        speaker_name=None,
        text=text,
        ts=datetime.now(UTC),
        is_final=True,
        raw={
            "source": "audio-worker.audio_chunk",
            "chunk_seq": x_chunk_seq,
            "audio_format": x_audio_format,
            "byte_size": len(wav_bytes),
            "saved_path": saved_path,
            "headers": {
                "x_audio_sample_rate": request.headers.get("x-audio-sample-rate"),
                "x_audio_channels": request.headers.get("x-audio-channels"),
                "x_audio_bits_per_sample": request.headers.get("x-audio-bits-per-sample"),
            },
        },
    )
    sent_to_brain = await brain_client.send_transcript(event)

    return {
        "ok": True,
        "chunk_seq": x_chunk_seq,
        "meeting_id": x_meeting_id,
        "text": text,
        "sent_to_brain": sent_to_brain is not None,
    }
