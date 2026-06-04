# Grey Cardinal Daemon for Windows

The MSI installs the Windows desktop audio daemon and safe helper scripts.
It does not contain `.env`, `INTERNAL_API_TOKEN`, Telegram tokens, or workspace secrets.

## Files

- `grey-cardinal-daemon.exe` - native Windows audio capture daemon.
- `install_or_start.ps1` - writes a local config and starts a short capture/upload.
- `smoke_upload_test.ps1` - uploads a generated WAV to `/api/audio/upload`.
- `open_logs.ps1` - opens `%LOCALAPPDATA%\GreyCardinal\Daemon\logs`.
- `config.example.toml` - production-safe config template.

## Install

```powershell
msiexec /i grey-cardinal-daemon-windows-x64.msi
```

Default install directory:

```text
C:\Program Files\Grey Cardinal Daemon\
```

## Quick Smoke Test

```powershell
Set-ExecutionPolicy -Scope Process Bypass
powershell -ExecutionPolicy Bypass -File "C:\Program Files\Grey Cardinal Daemon\smoke_upload_test.ps1" -BackendUrl "https://fishingteam.su" -MeetingId "daemon-smoke-windows"
```

The backend should return `ok: true`. Then open `https://fishingteam.su/app`,
click Refresh, and check the Daemon uploads panel.

## Capture And Upload

```powershell
Set-ExecutionPolicy -Scope Process Bypass
powershell -ExecutionPolicy Bypass -File "C:\Program Files\Grey Cardinal Daemon\install_or_start.ps1" -BackendUrl "https://fishingteam.su" -AgentId "agent-demo-001" -DurationSec 10 -CaptureMode microphone
```

For system audio capture, try:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Program Files\Grey Cardinal Daemon\install_or_start.ps1" -BackendUrl "https://fishingteam.su" -CaptureMode system_loopback -DurationSec 10
```

## Logs

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Program Files\Grey Cardinal Daemon\open_logs.ps1"
```

The default config path is `%LOCALAPPDATA%\GreyCardinal\Daemon\config.toml`.

## Current Limitations

The agent uploads WAV files to the backend. The public audio endpoint stores the
file and meeting metadata, but it does not yet run real ASR or create tasks
automatically from audio. Use the dashboard's chat/proposal flow for task
creation, or wire audio-worker/ASR to the public upload path in the next step.
