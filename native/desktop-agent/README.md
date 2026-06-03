# Grey Cardinal Desktop Agent

The desktop agent is a thin host-native audio client for the desktop-first flow.
The v0 Windows path captures the real default microphone, saves/debugs WAV chunks,
runs mock ASR over those chunks, and posts trusted desktop transcripts to
`brain-api` `/desktop/transcripts`. The legacy WASAPI render loopback path remains
available as `system_loopback_experimental` and must not be used as source of
truth for speaker identity.

P0 is Windows. macOS and Linux adapter stubs are present under `platform/macos` and `platform/linux`.

## Build

```powershell
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build --output-on-failure -C Release
```

Debug:

```powershell
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --config Debug
ctest --test-dir build --output-on-failure -C Debug
```

## Run

Start `brain-api` first:

```powershell
docker compose --profile full up --build
```

Then run the agent in another terminal:

```powershell
.\build\Release\grey-cardinal-agent.exe `
  --capture-mode microphone `
  --server http://localhost:8010 `
  --token dev-internal-token `
  --user-id <uuid> `
  --device-id <uuid> `
  --client-session-id <uuid> `
  --display-name "Петя" `
  --meeting-id MTG-1 `
  --save-chunks .\chunks
```

Other useful commands:

```powershell
.\build\Release\grey-cardinal-agent.exe --list-input-devices
.\build\Release\grey-cardinal-agent.exe --capture-mode microphone --duration-sec 10 --save-chunks C:\Temp\gc-mic --dry-run
.\build\Release\grey-cardinal-agent.exe --config config.toml
```

For a guided Windows validation run:

```powershell
.\scripts\windows\record_mic_test.ps1
```

Speak while the agent runs, then verify WAV chunks appear in
`C:\Temp\GreyCardinal\mic-test` and can be played.

## Config

The default Windows config path is:

```text
%LOCALAPPDATA%\GreyCardinal\Agent\config.toml
```

Example:

```toml
brain_api_url = "http://localhost:8010"
internal_token = "dev-internal-token"

user_id = ""
device_id = ""
client_session_id = ""
workspace_id = ""
display_name = ""
meeting_id = "MTG-1"

capture_mode = "microphone"
input_device_id = ""
chunk_ms = 3000
asr_provider = "mock"
mock_phrases = [
  "Я подготовлю оплату до завтра 18:00",
  "Беру websocket на себя до пятницы",
  "Аня, проверь интеграцию с YouGile сегодня вечером"
]
```

CLI flags override config values.

## Upload Contract

Microphone desktop mode sends:

```text
POST {brain_api_url}/desktop/transcripts
Content-Type: application/json
X-Internal-Token: <token>
X-GC-User-Id: <user_id>
X-GC-Device-Id: <device_id>
X-GC-Client-Session-Id: <client_session_id>
```

The JSON body is TranscriptEvent v2-shaped and includes `source.kind=desktop_app`,
`speaker.identity_source=authenticated_client`, `identity_confidence=1.0`,
`asr.provider=mock`, and microphone audio metadata. The server resolves trusted
speaker identity from the headers/session and rejects non-microphone desktop
capture.

`system_loopback_experimental` still uses the legacy `/audio/chunk` upload path
for compatibility with the old audio-worker validation flow.

## Logs

Windows logs are appended to:

```text
%LOCALAPPDATA%\GreyCardinal\Agent\logs\agent.log
```

The agent logs startup config, selected default input device, audio format,
`mic_rms=...` per chunk, saved WAV paths, upload responses, server errors, and
capture errors. It never logs raw audio text beyond mock ASR phrases.

## Installer

Install Inno Setup, then run:

```powershell
.\scripts\windows\build_installer.ps1
```

The installer is per-user, creates a Start Menu shortcut, can optionally create a Desktop shortcut, and can optionally add an HKCU Run entry for auto-start.

## Troubleshooting

- No microphone audio: verify Windows microphone permissions/input level and run `--list-input-devices`.
- Server unavailable: confirm brain-api is running and `curl http://localhost:8010/health` returns ok.
- Token mismatch: align `--token` with `INTERNAL_API_TOKEN`.
- Docker not running: start Docker Desktop and rebuild the `full` profile.
- Device format unsupported: common float32/PCM WASAPI mix formats are converted to mono PCM16. Other formats should be converted in a future adapter/resampler pass.
- Current MVP limitations: Windows microphone capture is real; ASR is mock by default; faster-whisper/SpeechKit are placeholders; VAD and diarization are not implemented yet; chunks are mono PCM16 WAV at the captured sample rate unless a future resampler is added.
