# Daemon Setup

Grey Cardinal ships a downloadable Windows daemon package from the existing
Daemon setup flow.

## Download

- Site flow: open `https://fishingteam.su`, click `Daemon setup`.
- Direct URL: `https://fishingteam.su/downloads/grey-cardinal-daemon-windows.zip`
- Version: `0.2.0`
- Built: `2026-06-04`
- Size: `77.7 KB`
- SHA256: `31F1089611D7C59ED74FA9BC81264823CD301AF5E8927AC47E975798DEDD0FDF`

## Package Contents

- `grey-cardinal-agent.exe` - Windows native audio capture agent.
- `install_or_start.ps1` - writes `%LOCALAPPDATA%\GreyCardinal\Agent\config.toml`
  and starts a short capture/upload.
- `smoke_upload_test.ps1` - generates a small WAV and uploads it to backend.
- `open_logs.ps1` - opens `%LOCALAPPDATA%\GreyCardinal\Agent\logs`.
- `config.example.toml` - production-safe config template.
- `README_DAEMON_WINDOWS.md` - package-local instructions.

No `.env`, `INTERNAL_API_TOKEN`, Telegram token, or other secret is included.

## Windows Quick Start

```powershell
Expand-Archive .\grey-cardinal-daemon-windows.zip -DestinationPath .\grey-cardinal-daemon-windows
cd .\grey-cardinal-daemon-windows
Set-ExecutionPolicy -Scope Process Bypass
.\smoke_upload_test.ps1 -BackendUrl "https://fishingteam.su" -MeetingId "daemon-smoke-windows"
```

Then open `https://fishingteam.su/app`, click `Refresh`, and check
`Daemon uploads`.

To record and upload a short microphone capture:

```powershell
.\install_or_start.ps1 -BackendUrl "https://fishingteam.su" -AgentId "agent-demo-001" -DurationSec 10 -CaptureMode microphone
```

To try system loopback:

```powershell
.\install_or_start.ps1 -BackendUrl "https://fishingteam.su" -DurationSec 10 -CaptureMode system_loopback
```

## Config

Default config path:

```text
%LOCALAPPDATA%\GreyCardinal\Agent\config.toml
```

Example:

```toml
backend_url = "https://fishingteam.su"
agent_id = "agent-demo-001"
meeting_id = ""
capture_mode = "microphone"
duration_sec = 10
output_dir = ""
dry_run = false
```

## Endpoints

- Agent/smoke upload: `POST /api/audio/upload`
- Upload visibility: `GET /api/meetings`
- Frontend page: `/download`
- Cockpit visibility: `/app`, `Daemon uploads`

## Verification

```powershell
curl.exe -I https://fishingteam.su/
curl.exe -I https://fishingteam.su/downloads/grey-cardinal-daemon-windows.zip
curl.exe -I https://fishingteam.su/api/health
```

Backend ingest smoke:

```powershell
.\smoke_upload_test.ps1 -BackendUrl "https://fishingteam.su" -MeetingId "daemon-smoke-windows"
curl.exe https://fishingteam.su/api/meetings
```

## Limitations

- The Windows package contains a real `.exe`, but not an MSI installer.
- Microphone/system loopback capture is implemented in the Windows native agent.
- The public audio upload path stores WAV and meeting metadata.
- Real ASR and automatic task creation are not wired to `/api/audio/upload` yet.
- The cockpit shows upload visibility via `Daemon uploads`; tasks are still
  created through the existing chat/proposal flow until audio-worker/ASR is
  connected to this public path.
