#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-https://fishingteam.su}"
AGENT_ID="${AGENT_ID:-linux-daemon-preview}"
MEETING_ID="${MEETING_ID:-daemon-smoke-linux-preview}"
WAV_PATH="${WAV_PATH:-/tmp/grey-cardinal-daemon-smoke.wav}"

python3 - "$WAV_PATH" <<'PY'
import math
import struct
import sys
import wave

path = sys.argv[1]
sample_rate = 8000
samples = sample_rate
with wave.open(path, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    for i in range(samples):
        value = int(12000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        wav.writeframes(struct.pack("<h", value))
PY

now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
curl -sS -X POST "${BACKEND_URL%/}/api/audio/upload" \
  -F "audio=@${WAV_PATH};type=audio/wav" \
  -F "agent_id=${AGENT_ID}" \
  -F "meeting_id=${MEETING_ID}" \
  -F "source=desktop_agent" \
  -F "started_at=${now}" \
  -F "ended_at=${now}"
echo
