# Grey Cardinal Audio Worker

`audio-worker` accepts WAV chunks from the host-native desktop agent, runs a small ASR abstraction, and forwards `TranscriptEvent` payloads to `brain-api`.

This is now the legacy/dev path. The production direction is authenticated desktop clients sending microphone transcripts directly to `brain-api` via `/desktop/transcripts`.

## Run with Docker

```powershell
docker compose --profile full up --build
curl http://localhost:8020/health
```

Pipeline validation from the repository root:

```powershell
.\scripts\windows\validate_audio_pipeline.ps1
```

## POST `/audio/chunk`

Headers:

- `X-Internal-Token`: must match `INTERNAL_API_TOKEN`
- `X-Meeting-Id`: meeting id for the transcript event
- `X-Chunk-Seq`: incrementing chunk number
- `X-Audio-Format`: `wav`

Body: `audio/wav` bytes. The worker rejects empty payloads and payloads without `RIFF`/`WAVE` WAV markers.

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

## Tests

```powershell
python -m pytest apps/audio-worker apps/brain-api
```

The default test path uses mock ASR and a fake brain client; it does not require real audio, Docker, or network access.

## Known limitations

- Mock ASR is the default for fast offline tests and legacy demos.
- `faster-whisper` is optional and CPU-backed in this MVP.
- No VAD or diarization yet; transcript events use `speaker_id=unknown`.
- The Windows loopback agent sends mono PCM16 WAV chunks at the captured sample rate unless future resampling is added, but loopback is experimental and not trusted speaker identity.
