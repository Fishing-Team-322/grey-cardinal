# Grey Cardinal Desktop App

Desktop-first client skeleton for authenticated microphone transcript flow.

The desktop app is the primary participant client. Telegram remains a notification and confirmation channel; `audio-worker` remains a legacy/dev path.

## Dev Run

```powershell
cd apps\desktop-app
npm install
npm run build
npm run dev
```

Expected backend:

```powershell
docker compose --profile full up --build
```

or local `brain-api` on `http://localhost:8010`.

## Flow

1. Register a dev identity/device.
2. Join a meeting such as `MTG-1`.
3. Start the native microphone agent from the generated command/script.
4. The agent captures real microphone WAV chunks, runs mock ASR, and posts v2-shaped desktop transcripts through `POST /desktop/transcripts`.
5. Review transcript status, task list, and gamification state.

Without Tauri, process launch is script-based:

```powershell
scripts\windows\start_desktop_agent_for_identity.ps1 `
  -BrainUrl "http://localhost:8010" `
  -Token "dev-internal-token" `
  -UserId "<uuid>" `
  -DeviceId "<uuid>" `
  -ClientSessionId "<uuid>" `
  -DisplayName "Петя" `
  -MeetingId "MTG-1" `
  -CaptureMode microphone
```

ASR is still mock in v0. Speaker identity comes from the authenticated desktop session, not from voice recognition.
