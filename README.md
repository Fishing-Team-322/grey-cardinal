# Grey Cardinal

Hackathon scaffold for the Grey Cardinal audio pipeline.

The desktop agent is a thin host-native audio client. On Windows it is a user-mode Core Audio client and does not install a kernel driver. It captures system output through WASAPI loopback and streams short audio chunks to the containerized Python pipeline. The common agent core is platform-neutral, so macOS/Linux require only new capture adapters.

## Run the server side

```powershell
docker compose --profile full up --build
```

Healthcheck:

```powershell
curl http://localhost:8010/health
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

Recent transcript events can be checked during a demo:

```powershell
curl -H "X-Internal-Token: dev-internal-token" http://localhost:8010/internal/audio/transcripts/recent
```

## Tests and validation

Python:

```powershell
python -m pytest apps/audio-worker apps/brain-api
```

C++ agent Release:

```powershell
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build --output-on-failure -C Release
cd ..\..
```

C++ agent Debug:

```powershell
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --config Debug
ctest --test-dir build --output-on-failure -C Debug
cd ..\..
```

Make targets, if Make is available:

```powershell
make test
make test-python
make test-agent
```

Compose config and scripted pipeline validation:

```powershell
docker compose --profile full config
.\scripts\windows\validate_audio_pipeline.ps1
```

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
.\build\Release\grey-cardinal-agent.exe --duration-sec 15 --save-chunks .\chunks
.\build\Release\grey-cardinal-agent.exe --config config.toml
```

Scripted Windows capture check:

```powershell
.\scripts\windows\run_agent_capture_test.ps1 -Seconds 15
```

Play browser/system audio while the script runs. Verify WAV files appear in `.\chunks`, play one back, and check `audio-worker` logs plus `brain-api` recent transcripts.

## Installer

Install Inno Setup, then run:

```powershell
.\scripts\windows\build_installer.ps1
```

The installer is per-user and writes app files under `{localappdata}\Programs\Grey Cardinal Agent`.

## Troubleshooting

- No system audio: play audio through the default Windows output device before starting capture, then try `--list-devices`.
- Server unavailable: confirm `docker compose --profile full up --build` is running and `curl http://localhost:8020/health` returns ok.
- Token mismatch: the agent `--token` must match `INTERNAL_API_TOKEN` in Docker Compose.
- Docker not running: start Docker Desktop before launching the compose stack.
- Device format unsupported: the Windows adapter handles common WASAPI float/PCM mix formats and writes mono PCM16 WAV chunks at the device sample rate. 16 kHz resampling is a TODO behind the existing chunking boundary.
- Current MVP limitations: Windows WASAPI loopback is real; macOS/Linux adapters are planned stubs; mock ASR is the default; faster-whisper is optional; VAD and diarization are not implemented yet; chunks are mono PCM16 WAV at the captured sample rate unless a future resampler is added.
