"""
Grey Cardinal ASR Service — faster-whisper HTTP backend.

Accepts WAV audio via POST /transcribe and returns a JSON transcript.

Start:
    pip install fastapi uvicorn faster-whisper
    python -m uvicorn main:app --host 0.0.0.0 --port 8030

Or via Docker:
    docker compose up asr-service

Agent config (native/desktop-agent/config.toml or CLI):
    asr_provider = "faster_whisper_http"
    asr_url      = "http://localhost:8030/transcribe"
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import time
import wave

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("asr-service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Grey Cardinal ASR Service", version="0.1.0")

# ── Model loading ────────────────────────────────────────────────────────────

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "ru")  # default Russian; None = auto-detect

_model = None


def get_model():
    global _model
    if _model is None:
        logger.info(
            f"Loading faster-whisper model={MODEL_SIZE} device={DEVICE} compute_type={COMPUTE_TYPE}"
        )
        t0 = time.time()
        try:
            from faster_whisper import WhisperModel

            _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
            logger.info(f"Model loaded in {time.time() - t0:.1f}s")
        except ImportError:
            logger.error("faster-whisper not installed. Run: pip install faster-whisper")
            raise
    return _model


# ── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL_SIZE, "device": DEVICE}


@app.post("/transcribe")
async def transcribe(request: Request):
    """
    Accept raw WAV audio and return a transcript.

    Request:
        Content-Type: audio/wav  (raw WAV bytes in body)

    Response:
        {
          "text": "распознанный текст",
          "provider": "faster_whisper",
          "model": "base",
          "language": "ru",
          "confidence": 0.85,
          "duration_ms": 3120
        }
    """
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=415,
            detail=f"Expected audio/* content-type, got: {content_type}",
        )

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty body")

    t0 = time.time()

    # Parse WAV to extract audio duration
    duration_ms = 0
    try:
        with wave.open(io.BytesIO(body)) as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                duration_ms = int(frames * 1000 / rate)
    except Exception:
        pass  # not a valid WAV, attempt anyway

    # Write to temp file (faster-whisper requires a file path)
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(body)
        tmp_path = tmp.name

    try:
        model = get_model()
        lang = LANGUAGE if LANGUAGE else None
        segments, info = model.transcribe(
            tmp_path,
            language=lang,
            beam_size=5,
            vad_filter=True,
        )
        text_parts = [seg.text.strip() for seg in segments if seg.text.strip()]
        text = " ".join(text_parts)

        # Compute average log probability as a proxy for confidence
        avg_logprob = getattr(info, "language_probability", None)
        confidence = round(float(avg_logprob), 4) if avg_logprob is not None else 0.8

        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info(
            f"transcribed {len(body)} bytes in {elapsed_ms}ms "
            f"| duration_ms={duration_ms} lang={info.language} text={text[:80]!r}"
        )

        return JSONResponse(
            {
                "text": text,
                "provider": "faster_whisper",
                "model": MODEL_SIZE,
                "language": info.language,
                "confidence": confidence,
                "duration_ms": duration_ms,
            }
        )

    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"faster-whisper not available: {e}") from e
    except Exception as e:
        logger.error(f"transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


@app.get("/")
def root():
    return {
        "service": "Grey Cardinal ASR",
        "endpoints": ["/health", "/transcribe"],
        "model": MODEL_SIZE,
        "usage": "POST /transcribe with Content-Type: audio/wav",
    }
