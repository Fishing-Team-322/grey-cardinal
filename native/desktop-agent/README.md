# Grey Cardinal Desktop Audio Agent

A lightweight Windows audio capture agent. Its only job is to record microphone
(or system loopback) audio and upload the resulting WAV file to the backend.
All transcription, speaker diarization, and task extraction happen server-side.

## Architecture

```
Desktop Agent
  → records audio (WASAPI)
  → saves temp WAV file
  → POST /api/audio/upload   (multipart/form-data)
  → backend processes everything
```

The agent has **no AI/LLM code**, no local speech recognition, and no task logic.

## Build

```powershell
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build --output-on-failure -C Release
```

## Run

Minimal — record until Ctrl+C and upload:

```powershell
.\build\Release\grey-cardinal-agent.exe `
  --backend http://localhost:8010 `
  --agent-id "agent-001"
```

Record for 60 seconds then upload automatically:

```powershell
.\build\Release\grey-cardinal-agent.exe `
  --backend http://localhost:8010 `
  --agent-id "agent-001" `
  --meeting-id "meet-abc123" `
  --duration-sec 60
```

Record and save WAV locally without uploading (for testing):

```powershell
.\build\Release\grey-cardinal-agent.exe `
  --backend http://localhost:8010 `
  --duration-sec 10 `
  --output-dir C:\recordings `
  --dry-run
```

List available input devices:

```powershell
.\build\Release\grey-cardinal-agent.exe --list-devices
```

## Config file

Default path: `%LOCALAPPDATA%\GreyCardinal\Daemon\config.toml`

```toml
backend_url  = "http://localhost:8010"
agent_id     = "agent-001"
meeting_id   = ""               # auto-generated UUID if empty
capture_mode = "microphone"     # microphone | system_loopback
duration_sec = 0                # 0 = until Ctrl+C
output_dir   = ""               # empty = %TEMP%\grey-cardinal
dry_run      = false
```

CLI flags override config file values.

## Upload endpoint

```
POST {backend_url}/api/audio/upload
Content-Type: multipart/form-data
```

Form fields:

| Field        | Type   | Example                        |
|-------------|--------|--------------------------------|
| `audio`     | file   | recording.wav (audio/wav)      |
| `agent_id`  | string | `"agent-001"`                  |
| `meeting_id`| string | `"550e8400-e29b-41d4-a716-..."` |
| `source`    | string | `"desktop_agent"`              |
| `started_at`| string | `"2024-01-15T10:30:00Z"`       |
| `ended_at`  | string | `"2024-01-15T10:35:00Z"`       |

Expected response:

```json
{
  "ok": true,
  "audio_id": "audio_123",
  "message": "Audio uploaded successfully"
}
```

### curl example

```bash
curl -X POST http://localhost:8010/api/audio/upload \
  -F "audio=@recording.wav;type=audio/wav" \
  -F "agent_id=agent-001" \
  -F "meeting_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "source=desktop_agent" \
  -F "started_at=2024-01-15T10:30:00Z" \
  -F "ended_at=2024-01-15T10:35:00Z"
```

## Status output

The agent prints one status line to stdout at each transition:

```
[recording]
[uploading]
[uploaded: audio_id=audio_123]
[error: upload failed]
```

## Logs

```
%LOCALAPPDATA%\GreyCardinal\Daemon\logs\daemon.log
```

## Module overview

| Module          | File(s)                        | Responsibility                        |
|----------------|-------------------------------|---------------------------------------|
| `AudioRecorder` | `audio_recorder.hpp/.cpp`     | Accumulates frames, writes WAV file   |
| `Uploader`      | `uploader.hpp/.cpp`           | multipart POST to backend             |
| `Config`        | `config.hpp/.cpp`             | Parses config file and CLI args       |
| `Logger`        | `logger.hpp/.cpp`             | Timestamped log to stdout + file      |
| `WavWriter`     | `wav_writer.hpp/.cpp`         | Encodes PCM → WAV bytes               |
| WASAPI capture  | `platform/windows/...`        | Windows microphone / loopback capture |

## Troubleshooting

- **No audio captured**: check Windows microphone permissions and run `--list-devices`.
- **Backend unreachable**: verify the server is running; the agent retries 3 times then
  prints the error and preserves the WAV file locally.
- **Wrong device**: use `--input-device-name` or `--input-device-index` to select a
  specific device from `--list-devices` output.
