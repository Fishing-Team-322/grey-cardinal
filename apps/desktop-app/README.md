# Grey Cardinal Desktop App

Real Tauri desktop application for authenticated microphone transcript flow.

The desktop app is the primary participant client. It opens as a real OS window, controls
the C++ audio agent directly via Tauri commands, and communicates only with `brain-api`.

## Quick Start (Tauri desktop app — main path)

```powershell
# 1. Build the C++ agent sidecar (required for real mic capture)
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release

# 2. Start brain-api backend
docker compose up --build brain-api postgres

# 3. Run the Tauri desktop app (opens a real window)
cd apps\desktop-app
npm install
npm run tauri:dev

# 4. Or build a Windows installer
npm run tauri:build
```

## Browser-Only Dev (fallback, no Tauri)

```powershell
cd apps\desktop-app
npm install
npm run dev
```

Opens at http://localhost:5174. All Tauri commands are stubbed — shows PowerShell
fallback commands in the Daemon panel for manual agent control.

## Demo Flow

1. Register device → Start session
2. Join meeting `MTG-1`
3. Microphone panel → Refresh → select your mic
4. **▶ Start Listening** — Tauri spawns C++ agent
5. Agent records mic → sends WAV chunks → brain-api creates transcripts
6. Proposals appear in the Tasks panel → click **Confirm** → task + XP

## Real ASR

Set ASR provider to `faster_whisper_http` in the UI.

Start the ASR service:
```powershell
docker compose --profile desktop up asr-service
# or: cd apps\asr-service && uvicorn main:app --port 8030
```

## Mock ASR (clearly labeled)

When ASR provider is `mock`, the UI shows: **⚠ MOCK — simulated phrases, not real speech**.
The agent cycles through pre-configured Russian task phrases.

## Fallback Scripts (dev diagnostics)

```powershell
scripts\windows\diagnose_microphones.ps1
scripts\windows\start_desktop_agent_for_identity.ps1 -BrainUrl "http://localhost:8000" `
  -Token "dev-internal-token" -UserId "<uuid>" -DeviceId "<uuid>" `
  -ClientSessionId "<uuid>" -DisplayName "Петя" -MeetingId "MTG-1" -CaptureMode microphone
```

Scripts are **fallback dev tools** only — the main flow is through the Tauri UI.

## Build Output

```
src-tauri\target\release\bundle\msi\Grey Cardinal_0.1.0_x64_en-US.msi
src-tauri\target\release\bundle\nsis\Grey Cardinal_0.1.0_x64-setup.exe
```
