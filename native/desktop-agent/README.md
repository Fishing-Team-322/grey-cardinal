# Grey Cardinal Desktop Agent

The desktop agent is a thin host-native audio client. On Windows it is a user-mode Core Audio client and does not install a kernel driver. It captures system output through WASAPI loopback and streams short audio chunks to the containerized Python pipeline. The common agent core is platform-neutral, so macOS/Linux require only new capture adapters.

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

Start the Docker pipeline first:

```powershell
docker compose --profile full up --build
```

Then run the agent in another terminal:

```powershell
.\build\Release\grey-cardinal-agent.exe `
  --server http://localhost:8020 `
  --token dev-internal-token `
  --meeting-id demo-meeting `
  --save-chunks .\chunks
```

Other useful commands:

```powershell
.\build\Release\grey-cardinal-agent.exe --list-devices
.\build\Release\grey-cardinal-agent.exe --dry-run --save-chunks .\chunks
.\build\Release\grey-cardinal-agent.exe --dry-run-save-only --duration-sec 15 --save-chunks .\chunks
.\build\Release\grey-cardinal-agent.exe --config config.toml
```

For a guided Windows validation run:

```powershell
.\scripts\windows\run_agent_capture_test.ps1 -Seconds 15
```

Play browser/system audio while the agent runs, then verify WAV chunks appear in `.\chunks` and can be played.

## Config

Copy `config.example.toml` to `config.toml`:

```toml
server_url = "http://localhost:8020"
internal_token = "dev-internal-token"
meeting_id = "demo-meeting"
chunk_ms = 3000
duration_sec = 0
save_chunks = "./chunks"
dry_run = false
```

The parser is intentionally small and supports the simple TOML-style `key = value` fields above.

## Upload Contract

The agent sends:

```text
POST {server_url}/audio/chunk
Content-Type: audio/wav
X-Internal-Token: <token>
X-Meeting-Id: <meeting_id>
X-Chunk-Seq: <seq>
X-Audio-Format: wav
X-Audio-Sample-Rate: <sample_rate>
X-Audio-Channels: 1
X-Audio-Bits-Per-Sample: 16
```

For P0 the Windows adapter converts the WASAPI mix format to mono PCM16 WAV at the device sample rate. Resampling to 16 kHz is a planned improvement behind the existing `AudioFrame`/`ChunkUploader` boundary.

## Logs

Windows logs are appended to:

```text
%LOCALAPPDATA%\GreyCardinal\Agent\logs\agent.log
```

The agent logs startup config, selected default render device, audio format, chunk creation, upload responses, server errors, and capture errors. It never logs raw audio.

## Installer

Install Inno Setup, then run:

```powershell
.\scripts\windows\build_installer.ps1
```

The installer is per-user, creates a Start Menu shortcut, can optionally create a Desktop shortcut, and can optionally add an HKCU Run entry for auto-start.

## Troubleshooting

- No system audio: verify Windows is playing through the default render device and run `--list-devices`.
- Server unavailable: confirm Docker is running and `curl http://localhost:8020/health` returns ok.
- Token mismatch: align `--token` with `INTERNAL_API_TOKEN`.
- Docker not running: start Docker Desktop and rebuild the `full` profile.
- Device format unsupported: common float32/PCM WASAPI mix formats are supported. Other formats should be converted in a future adapter/resampler pass.
- Current MVP limitations: Windows WASAPI loopback is real; macOS/Linux adapters are planned stubs; mock ASR is the default server path; faster-whisper is optional; VAD and diarization are not implemented yet; chunks are mono PCM16 WAV at the captured sample rate unless a future resampler is added.
