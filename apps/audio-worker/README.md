# Grey Cardinal Audio Worker

`audio-worker` accepts WAV chunks from the host-native desktop agent, runs a small ASR abstraction, and forwards `TranscriptEvent` payloads to `brain-api`.

## Run with Docker

```powershell
docker compose --profile full up --build
curl http://localhost:8020/health
```

## POST `/audio/chunk`

Headers:

- `X-Internal-Token`: must match `INTERNAL_API_TOKEN`
- `X-Meeting-Id`: meeting id for the transcript event
- `X-Chunk-Seq`: incrementing chunk number
- `X-Audio-Format`: `wav`

Body: `audio/wav` bytes.

Smoke test:

```powershell
.\apps\audio-worker\scripts\send_mock_wav.ps1 -Server http://localhost:8020 -Token dev-internal-token -MeetingId demo-meeting
```

## ASR settings

- `AUDIO_ASR_PROVIDER=mock|faster_whisper`
- `AUDIO_MOCK_TEXT=Петя, сделай оплату к четвергу`
- `AUDIO_WORKER_SAVE_CHUNKS=false`
- `AUDIO_WORKER_CHUNKS_DIR=/tmp/grey-cardinal-audio-chunks`
- `AUDIO_FASTER_WHISPER_MODEL=base`

`faster-whisper` is optional. The worker imports it only when `AUDIO_ASR_PROVIDER=faster_whisper`, so the default mock mode stays lightweight.

