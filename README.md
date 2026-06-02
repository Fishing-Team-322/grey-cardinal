# Grey Cardinal

Hackathon scaffold for the Grey Cardinal audio pipeline.

The desktop agent is a thin host-native audio client. On Windows it is a user-mode Core Audio client and does not install a kernel driver. It captures system output through WASAPI loopback and streams short audio chunks to the containerized Python pipeline. The common agent core is platform-neutral, so macOS/Linux require only new capture adapters.

## Run the server side

```powershell
docker compose --profile full up --build
```

Healthcheck:

```powershell
curl http://localhost:8020/health
```

The `audio-worker` listens on `http://localhost:8020` so the host-native desktop agent can reach it from Windows. Audio capture is intentionally not run inside Docker because containers do not have direct, portable access to the host desktop audio stack.

## Mock WAV test

```powershell
.\apps\audio-worker\scripts\send_mock_wav.ps1 `
  -Server http://localhost:8020 `
  -Token dev-internal-token `
  -MeetingId demo-meeting
```

Expected result: `audio-worker` returns JSON with mock transcript text and sends a `TranscriptEvent` to `brain-api`.

## Build the C++ agent

```powershell
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

## Run the agent

```powershell
.\build\Release\grey-cardinal-agent.exe `
  --server http://localhost:8020 `
  --token dev-internal-token `
  --meeting-id demo-meeting `
  --save-chunks .\chunks
```

Useful flags:

```powershell
.\build\Release\grey-cardinal-agent.exe --list-devices
.\build\Release\grey-cardinal-agent.exe --dry-run --save-chunks .\chunks
.\build\Release\grey-cardinal-agent.exe --config config.toml
```

## Installer

Install Inno Setup, build the C++ agent in Release mode, then compile:

```powershell
iscc .\native\desktop-agent\installer\windows\grey-cardinal-agent.iss
```

The installer is per-user and writes app files under `{localappdata}\Programs\Grey Cardinal Agent`.

## Troubleshooting

- No system audio: play audio through the default Windows output device before starting capture, then try `--list-devices`.
- Server unavailable: confirm `docker compose --profile full up --build` is running and `curl http://localhost:8020/health` returns ok.
- Token mismatch: the agent `--token` must match `INTERNAL_API_TOKEN` in Docker Compose.
- Docker not running: start Docker Desktop before launching the compose stack.
- Device format unsupported: the Windows adapter handles common WASAPI float/PCM mix formats and writes mono PCM16 WAV chunks at the device sample rate. 16 kHz resampling is a TODO behind the existing chunking boundary.

