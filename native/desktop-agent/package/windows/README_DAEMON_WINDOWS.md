# Grey Cardinal Daemon for Windows

This package contains the Windows desktop audio agent and safe helper scripts.
It does not contain `.env`, `INTERNAL_API_TOKEN`, Telegram tokens, or workspace secrets.

## Files

- `grey-cardinal-agent.exe` - native Windows audio capture agent.
- `install_or_start.ps1` - writes a local config and starts a short capture/upload.
- `smoke_upload_test.ps1` - uploads a generated WAV to `/api/audio/upload`.
- `open_logs.ps1` - opens `%LOCALAPPDATA%\GreyCardinal\Agent\logs`.
- `config.example.toml` - production-safe config template.

## Quick Smoke Test

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\smoke_upload_test.ps1 -BackendUrl "https://fishingteam.su" -MeetingId "daemon-smoke-windows"
```

The backend should return `ok: true`. Then open `https://fishingteam.su/app`,
click Refresh, and check the Daemon uploads panel.

## Capture And Upload

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_or_start.ps1 -BackendUrl "https://fishingteam.su" -AgentId "agent-demo-001" -DurationSec 10 -CaptureMode microphone
```

For system audio capture, try:

```powershell
.\install_or_start.ps1 -BackendUrl "https://fishingteam.su" -CaptureMode system_loopback -DurationSec 10
```

## Logs

```powershell
.\open_logs.ps1
```

The default config path is `%LOCALAPPDATA%\GreyCardinal\Agent\config.toml`.

## Current Limitations

The agent uploads WAV files to the backend. The public audio endpoint stores the
file and meeting metadata, but it does not yet run real ASR or create tasks
automatically from audio. Use the dashboard's chat/proposal flow for task
creation, or wire audio-worker/ASR to the public upload path in the next step.
