"""
Grey Cardinal ASR Service — faster-whisper HTTP backend with post-correction.

POST /transcribe  — accept raw WAV, return JSON transcript
GET  /health      — liveness check

Environment:
    WHISPER_MODEL        = small   (tiny|base|small|medium|large-v3)
    WHISPER_DEVICE       = cpu
    WHISPER_COMPUTE_TYPE = int8
    WHISPER_LANGUAGE     = ru
    YANDEX_SPELLER       = true    (enable YandexSpeller post-correction)
    WHISPER_PROMPT       = ""      (optional domain hint fed to Whisper)
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import tempfile
import time
import wave

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("asr-service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Grey Cardinal ASR Service", version="0.2.0")

# ── Config ───────────────────────────────────────────────────────────────────

MODEL_SIZE    = os.environ.get("WHISPER_MODEL", "small")
DEVICE        = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE  = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
LANGUAGE      = os.environ.get("WHISPER_LANGUAGE", "ru") or None
SPELLER_ON    = os.environ.get("YANDEX_SPELLER", "true").lower() in {"1", "true", "yes"}

# Domain vocabulary hint — helps Whisper recognise names and terms correctly.
# Append your own terms here or override via env WHISPER_PROMPT.
_DEFAULT_PROMPT = (
    "Совещание проектной команды. Участники: Петя, Аня, Дима, Коля, Катя. "
    "Задачи, дедлайны, оплата, интеграция, релиз, YouGile, Grey Cardinal."
)
WHISPER_PROMPT = os.environ.get("WHISPER_PROMPT", _DEFAULT_PROMPT).strip() or None

# ── Model ────────────────────────────────────────────────────────────────────

_model = None


def get_model():
    global _model
    if _model is None:
        logger.info(
            "Loading faster-whisper model=%s device=%s compute_type=%s",
            MODEL_SIZE,
            DEVICE,
            COMPUTE_TYPE,
        )
        t0 = time.time()
        from faster_whisper import WhisperModel
        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        logger.info("Model loaded in %.1fs", time.time() - t0)
    return _model


# ── YandexSpeller post-correction ────────────────────────────────────────────

_SPELLER_URL = "https://speller.yandex.net/services/spellservice.json/checkText"


async def yandex_spell_correct(text: str, lang: str = "ru") -> str:
    """
    Call YandexSpeller free API to fix spelling errors in ASR output.
    Falls back to original text on any error (never blocks the response).

    Handles context-aware corrections like "пить я" → proper name,
    missing spaces, number/word confusion, etc.
    """
    if not text.strip():
        return text
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                _SPELLER_URL,
                data={"text": text, "lang": lang, "options": 518},
                # options=518: ignore URLs (2) + ignore digits (8) +
                #              find repeat words (16) + ignore proper nouns (0)
                #              + auto-apply first suggestion (512)
            )
            resp.raise_for_status()
            corrections = resp.json()
    except Exception as exc:
        logger.debug("YandexSpeller unavailable: %s", exc)
        return text

    if not corrections:
        return text

    # Apply corrections from end to start to preserve char positions.
    result = list(text)
    for item in sorted(corrections, key=lambda x: x["pos"], reverse=True):
        if not item.get("s"):
            continue
        pos   = item["pos"]
        length = item["len"]
        fix   = item["s"][0]
        result[pos : pos + length] = list(fix)

    corrected = "".join(result)
    if corrected != text:
        logger.info("Speller: %r → %r", text, corrected)
    return corrected


# ── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {
        "ok": True,
        "model": MODEL_SIZE,
        "device": DEVICE,
        "speller": SPELLER_ON,
    }


@app.post("/transcribe")
async def transcribe(request: Request):
    """
    Accept raw WAV bytes (Content-Type: audio/wav) and return a JSON transcript.

    Response:
        {
          "text": "...",           # corrected transcript
          "raw_text": "...",       # raw Whisper output before correction
          "provider": "faster_whisper",
          "model": "small",
          "language": "ru",
          "confidence": 0.93,
          "duration_ms": 4200,
          "speller_applied": true
        }
    """
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("audio/"):
        raise HTTPException(status_code=415, detail=f"Expected audio/*, got: {content_type}")

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty body")

    t0 = time.time()

    # WAV duration for logging
    duration_ms = 0
    with contextlib.suppress(Exception), wave.open(io.BytesIO(body)) as wf:
        frames, rate = wf.getnframes(), wf.getframerate()
        if rate > 0:
            duration_ms = int(frames * 1000 / rate)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(body)
        tmp_path = tmp.name

    try:
        model = get_model()
        segments, info = model.transcribe(
            tmp_path,
            language=LANGUAGE,
            beam_size=5,
            best_of=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            condition_on_previous_text=False,
            initial_prompt=WHISPER_PROMPT,
        )
        raw_text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())

        # Post-correction with YandexSpeller
        corrected = raw_text
        speller_applied = False
        if SPELLER_ON and raw_text:
            corrected = await yandex_spell_correct(raw_text, lang=info.language or "ru")
            speller_applied = corrected != raw_text

        confidence = round(float(getattr(info, "language_probability", 0.8)), 4)
        elapsed_ms = int((time.time() - t0) * 1000)

        logger.info(
            "transcribed %d bytes in %dms | audio=%dms lang=%s text=%r",
            len(body), elapsed_ms, duration_ms, info.language, corrected[:80],
        )

        return JSONResponse({
            "text":            corrected,
            "raw_text":        raw_text,
            "provider":        "faster_whisper",
            "model":           MODEL_SIZE,
            "language":        info.language,
            "confidence":      confidence,
            "duration_ms":     duration_ms,
            "speller_applied": speller_applied,
        })

    except Exception as exc:
        logger.error("transcription error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


@app.get("/")
def root():
    return {
        "service": "Grey Cardinal ASR",
        "version": "0.2.0",
        "model":   MODEL_SIZE,
        "endpoints": ["/health", "/transcribe"],
    }
