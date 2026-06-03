# Desktop-First Audio Architecture

Grey Cardinal is moving away from one mixed system-audio daemon as the production source of truth.

## Why Not System Audio

System loopback captures everything: meeting speech, browser audio, music, videos, and notification sounds. It also gives the server a mixed stream where speaker identity must be guessed. That is useful for demos and diagnostics, but it is the wrong production trust model.

## Identity Rule

Speaker identity is not voice recognition.

```text
Petya is Petya because:
- Petya is logged into the desktop app
- the transcript came from Petya's registered device/session
- the capture mode is microphone
```

The trusted desktop transcript shape is:

```text
source.kind = desktop_app
source.user_id = authenticated user
source.device_id = registered device
source.client_session_id = active session
source.capture_mode = microphone

speaker.identity_source = authenticated_client
speaker.identity_confidence = 1.0
```

## Flow

```text
Desktop App user microphone
  -> POST /desktop/transcripts
  -> brain-api trusted meeting timeline
  -> task proposal
  -> Telegram/Desktop confirmation
  -> task lifecycle
  -> gamification state
```

Each participant installs the desktop app. The meeting timeline is assembled from multiple authenticated microphone clients, not one mixed room/system stream.

## Brain API Ownership

`brain-api` owns devices, client sessions, meeting participants, transcript ingest, extraction, task lifecycle, board integration, reminders, websocket events, and gamification. The desktop app never talks directly to PostgreSQL or YouGile.

## Self-Assignment

When Petya's authenticated desktop client sends:

```text
Я подготовлю оплату до завтра
```

the proposal assignee is Petya with server-side trusted identity. If Petya says:

```text
Аня, проверь интеграцию с YouGile сегодня вечером
```

the extractor may assign Anya if she is a known workspace user. If no executor is explicit and there is no self-reference, assignee stays unknown.

## Telegram, Audio Worker, Native Agent

Telegram remains the notification, confirmation, reminder, and demo fallback channel.

`audio-worker` remains a legacy/mock pipeline that posts `/internal/audio/transcript`. It is not the production speaker identity source.

`native/desktop-agent` still contains the Windows WASAPI loopback MVP, but that mode is explicitly `system_loopback_experimental`. The production default capture mode is `microphone`; the desktop app mock microphone path is the current desktop-first skeleton.

## Fallbacks

Allowed optional modes:

- `microphone`
- `system_loopback_experimental`
- `mixed_meeting_experimental`
- `mock`

Only authenticated desktop microphone transcripts are trusted for speaker identity.

---

## Grey Cardinal Desktop v0 — Tauri App

The desktop app is now a real Tauri (Rust + React) application, not a browser tab.

### Stack

```
Tauri (Rust shell)  +  React/TypeScript UI  =  apps/desktop-app
C++ native agent                            =  native/desktop-agent
Python faster-whisper ASR service           =  apps/asr-service   (optional, for real ASR)
brain-api                                   =  all business logic
```

### Prerequisites

- **Rust** (stable, 1.75+): https://rustup.rs
- **Node.js** 20+ with npm
- **C++ build tools** (Windows): Visual Studio Build Tools 2022, CMake 3.20+
- **Docker** (optional, for brain-api and asr-service)

### Running the Desktop App

**1. Start the backend:**

```powershell
# From repo root
docker compose up --build brain-api postgres
# Or locally: cd apps/brain-api && uvicorn main:app --port 8000
```

**2. Build the C++ agent (required for real microphone capture):**

```powershell
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
# Agent binary: native\desktop-agent\build\Release\grey-cardinal-agent.exe
```

**3. Run the Tauri desktop app:**

```powershell
cd apps\desktop-app
npm install
npm run tauri:dev     # opens a real desktop window
# Or to build an installer:
npm run tauri:build
```

### Demo Flow

1. App opens as a real desktop window (not a browser tab)
2. Enter Brain URL, internal token, display name → **Register device**
3. Click **Start session**
4. Enter meeting ID (e.g. `MTG-1`) → **Join meeting**
5. In the Microphone panel: click **Refresh** → select your mic from the dropdown
6. Click **▶ Start Listening** — Tauri spawns the C++ agent sidecar
7. Agent records your mic, sends chunks to brain-api via `/desktop/transcripts`
8. Agent panel shows live log lines with `mic_rms`, `mic_peak`, upload status
9. After ~3 seconds a transcript arrives → a proposal appears in the Tasks panel
10. Click **Confirm** on the proposal → it becomes a task, XP increases
11. Click **■ Stop Listening** — agent process is terminated cleanly

### Real ASR (Option A — faster-whisper HTTP service)

```powershell
# Start ASR service:
docker compose --profile desktop up asr-service

# Or locally:
cd apps\asr-service
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8030
```

In the desktop app UI, set ASR provider to `faster_whisper_http`. The agent will POST
WAV chunks to `http://localhost:8030/transcribe` and receive real Russian speech recognition.

Model defaults: `base`, Russian language, CPU inference.
Override with env vars: `WHISPER_MODEL=small`, `WHISPER_LANGUAGE=ru`.

### Mock ASR (clearly labeled)

When ASR provider is `mock`:
- The UI shows a warning badge: **⚠ MOCK — simulated phrases, not real speech**
- The agent log shows: `WARN ASR: mock -- transcripts are simulated phrases`
- Mock phrases cycle through the configured list (default: task-like Russian phrases)
- Useful for testing the full pipeline (transcript → proposal → task → XP) without a microphone

### Diagnostics (fallback scripts)

Scripts in `scripts/windows/` remain as fallback dev tools:

```powershell
.\scripts\windows\diagnose_microphones.ps1
.\scripts\windows\record_mic_test.ps1
.\scripts\windows\start_desktop_agent_for_identity.ps1
.\scripts\windows\validate_desktop_transcript_flow.ps1
```

These are **not the main flow** — the main flow is through the Tauri UI.

### Build Output (Windows installer)

After `npm run tauri:build`:

```
apps\desktop-app\src-tauri\target\release\bundle\msi\Grey Cardinal_0.1.0_x64_en-US.msi
apps\desktop-app\src-tauri\target\release\bundle\nsis\Grey Cardinal_0.1.0_x64-setup.exe
```

The bundle includes or locates `grey-cardinal-agent.exe` as a bundled resource.

### Agent Binary Location (dev vs release)

The Tauri app locates the agent in this priority order:

1. `GREY_CARDINAL_AGENT_EXE` env var (explicit override)
2. Alongside the Tauri `.exe` in release bundle
3. Tauri resource directory
4. `native/desktop-agent/build/Release/grey-cardinal-agent.exe` (dev, relative to CWD)

### TODO Before Demo

- [ ] Icons: replace placeholder icons in `src-tauri/icons/` with real app icons
- [ ] Sign the Windows installer (optional for internal demo)
- [ ] Test with real microphone on Windows (WASAPI requires Windows to run)
- [ ] ASR service: test faster-whisper model download on first start
- [ ] Websocket live updates from brain-api (currently polling every 2s)
