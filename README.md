# Grey Cardinal

AI meeting agent: records audio on the desktop, processes it on the backend, extracts tasks.

## Architecture

```
Desktop Agent (Windows C++)
  → records mic/loopback audio
  → POST /api/audio/upload  →  Brain API (FastAPI + PostgreSQL)
                                  → stores audio file
                                  → queues for processing
                                  → extracts tasks (LLM or heuristic)
Frontend Dashboard (React)
  ← GET /api/meetings
  ← GET /api/meetings/{id}
  ← WebSocket /ws/events (live task events)
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| brain-api | 8000 | Main backend (FastAPI + PostgreSQL) |
| telegram-bot | 8010 | Telegram bot for task management |
| audio-worker | 8020 | Audio processing worker |
| frontend-dashboard | 5173 | React dashboard |

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env — set INTERNAL_API_TOKEN, optionally TELEGRAM_BOT_TOKEN etc.
docker compose up --build
```

Open http://localhost:5173 for the dashboard.

## Run backend only (for desktop agent demo)

```bash
docker compose up brain-api postgres --build
# backend available at http://localhost:8000
```

## Public API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/audio/upload` | Upload WAV from desktop agent |
| GET | `/api/meetings` | List all meetings |
| GET | `/api/meetings/{id}` | Meeting detail with audios |
| GET | `/api/meetings/{id}/status` | Meeting status |
| GET | `/api/meetings/{id}/tasks` | Tasks for meeting |

### Health check

```bash
curl http://localhost:8000/api/health
# {"ok":true,"service":"backend","status":"running"}
```

### Upload audio (curl example)

```bash
curl -X POST http://localhost:8000/api/audio/upload \
  -F "audio=@recording.wav;type=audio/wav" \
  -F "agent_id=agent-001" \
  -F "meeting_id=my-meeting-123" \
  -F "source=desktop_agent" \
  -F "started_at=2026-06-03T10:00:00Z" \
  -F "ended_at=2026-06-03T10:05:00Z"
```

Response:
```json
{"ok":true,"audio_id":"audio_a1b2c3d4e5f6","meeting_id":"my-meeting-123","status":"uploaded","message":"Audio uploaded successfully"}
```

### List meetings

```bash
curl http://localhost:8000/api/meetings
```

## Telemost bot mode

Two audio source modes are supported. The backend treats both identically — the only difference is the `source` field.

```
1. Desktop agent mode:
   local C++ app records mic/loopback audio and uploads it.
   source = "desktop_agent"

2. Telemost bot mode:
   backend creates a bot session for a Telemost meeting URL.
   Current implementation is demo/mock: manages session state only.
   Real bot joiner (browser automation / Telemost SDK) can be plugged
   into TelemostSessionManager.create() in telemost.py later.
   source = "telemost_bot"
```

### Telemost bot endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/telemost/join` | Start bot session |
| GET | `/api/telemost/{bot_session_id}/status` | Get session status |
| POST | `/api/telemost/{bot_session_id}/leave` | Stop bot session |

### Start bot

```bash
curl -X POST http://localhost:8000/api/telemost/join \
  -H "Content-Type: application/json" \
  -d '{"meeting_url":"https://telemost.yandex.ru/j/demo","meeting_id":"demo"}'
```

Response:
```json
{"ok":true,"meeting_id":"demo","bot_session_id":"bot_abc123","status":"joining","message":"Telemost bot join requested"}
```

### Check bot status

```bash
curl http://localhost:8000/api/telemost/bot_abc123/status
```

### Stop bot

```bash
curl -X POST http://localhost:8000/api/telemost/bot_abc123/leave
```

### Audio upload with telemost_bot source

```bash
curl -X POST http://localhost:8000/api/audio/upload \
  -F "audio=@recording.wav;type=audio/wav" \
  -F "agent_id=bot-001" \
  -F "meeting_id=demo" \
  -F "source=telemost_bot"
```

Allowed `source` values: `desktop_agent`, `telemost_bot`. Unknown values return 400.

### Bot session statuses

`created` → `joining` → `joined` → `recording` → `uploading` → `uploaded` → `left` | `error`

## Desktop Agent (Windows)

The desktop agent captures microphone audio and uploads it to the backend. It does **not** do any AI processing.

### Build

```powershell
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

### Configure

Copy `native/desktop-agent/config.example.toml` to  
`%LOCALAPPDATA%\GreyCardinal\Agent\config.toml` and set `backend_url`.

### Run

```powershell
# Record until Ctrl+C, then upload
.\build\Release\grey-cardinal-agent.exe --backend http://localhost:8000 --agent-id agent-001

# Record for 60 seconds
.\build\Release\grey-cardinal-agent.exe --duration-sec 60

# List audio devices
.\build\Release\grey-cardinal-agent.exe --list-devices

# Test without upload
.\build\Release\grey-cardinal-agent.exe --duration-sec 10 --dry-run
```

Status output:
```
[recording]
[uploading]
[uploaded: audio_id=audio_abc123]
```

## Frontend Dashboard

```bash
cd apps/frontend-dashboard
npm install
npm run dev   # http://localhost:5173
```

Set `VITE_API_BASE_URL=http://localhost:8000` in `.env` if backend is not on localhost.

## Tests

### Backend API tests (no PostgreSQL required)

```bash
cd apps/brain-api
pip install -e .[dev]
pip install python-multipart
pytest tests/test_public_api.py tests/test_telemost.py -v
```

### All backend tests (requires PostgreSQL via Docker)

```bash
docker compose up postgres -d
pytest apps/brain-api/tests/ -v
```

### Desktop agent tests

```powershell
cd native\desktop-agent
cmake -S . -B build -DBUILD_TESTING=ON
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
```

## Audio file storage

Uploaded audio files are stored at:
```
{UPLOADS_DIR}/{meeting_id}/{audio_id}.wav
```

Default `UPLOADS_DIR`: `/tmp/gc-uploads` (override with env var `UPLOADS_DIR`).

## Environment variables

Key variables (see `.env.example` for full list):

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERNAL_API_TOKEN` | `dev-internal-token` | Shared secret for internal APIs |
| `DATABASE_URL` | PostgreSQL URL | Backend DB |
| `UPLOADS_DIR` | `/tmp/gc-uploads` | Audio file storage |
| `LLM_API_KEY` | — | OpenAI-compatible API key for task extraction |
| `BOARD_PROVIDER` | `mock` | Task board: `mock` or `yougile` |
