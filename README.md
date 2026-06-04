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

## Brain pipeline (chat → proposal → board)

Autonomous demo pipeline (no PostgreSQL, no LLM required). A message is turned
into a **pending proposal** by a real rule-based Russian extractor; a task is
created only after explicit confirmation. Nothing is fabricated — no fake tasks,
no fake transcription. See **[DEMO.md](DEMO.md)** for the full curl walkthrough.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat/messages` | Ingest message → task proposal (or `has_task=false`) |
| GET | `/api/task-proposals` | List proposals (optional `?status=pending`) |
| POST | `/api/task-proposals/{id}/confirm` | Confirm → create task in board `todo` |
| POST | `/api/task-proposals/{id}/reject` | Reject → no task |
| GET | `/api/tasks` | List created tasks |
| GET | `/api/board` | Board columns: `todo` / `in_progress` / `done` |
| POST | `/api/tasks/{id}/move` | Move task between statuses |
| GET | `/api/digest/evening` | Evening digest from real proposals/tasks |
| GET | `/api/meetings/{id}/transcript` | Transcript, or honest `unavailable` if no STT |
| POST | `/api/meetings/{id}/transcript` | Manual/demo transcript → same extractor → proposal |

```bash
curl -X POST http://localhost:8000/api/chat/messages \
  -H "Content-Type: application/json" \
  -d '{"author":"Денис","text":"Нужно оплатить сервер до четверга, ответственный Иван"}'
```

> **Speech-to-text:** no STT provider is configured, so audio is not auto-transcribed.
> `GET /api/meetings/{id}/transcript` returns `transcription_status: "unavailable"`
> rather than inventing a transcript. Use the manual transcript endpoint for the demo.

## YouGile board integration

When a proposal is confirmed, the task lands on the **local board** and is also
synced to **YouGile** (REST API v2) when enabled. The two modes:

- **Local board mode** (default, `YOUGILE_ENABLED=false`): tasks live on the local
  board only; the integration honestly reports `status=disabled`. Nothing is faked.
- **Real YouGile mode** (`YOUGILE_ENABLED=true` + credentials): confirmed tasks are
  created in the YouGile `TODO` column; moves are mirrored to the matching column.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/integrations/yougile/status` | `disabled` / `connected` / `error` + config |
| GET | `/api/integrations/yougile/columns` | Configured column IDs (+ verified against API) |
| POST | `/api/tasks/{id}/sync-yougile` | Retry create/move sync after an error |

```env
YOUGILE_ENABLED=true
YOUGILE_API_BASE_URL=https://ru.yougile.com    # auth: Authorization: Bearer <key>
YOUGILE_API_KEY=<key>
YOUGILE_BOARD_ID=<board id>
YOUGILE_COLUMN_TODO_ID=<todo column id>
YOUGILE_COLUMN_IN_PROGRESS_ID=<in-progress column id>
YOUGILE_COLUMN_DONE_ID=<done column id>
YOUGILE_USER_MAP={"Иван":"user_id_1"}          # optional assignee → user id
```

```bash
curl http://localhost:8000/api/integrations/yougile/status
# disabled: {"ok":true,"enabled":false,"configured":false,"status":"disabled","reason":"..."}
# enabled:  {"ok":true,"enabled":true,"configured":true,"status":"connected","board_id":"..."}
```

Confirmed tasks expose `yougile_status` (`disabled|pending|synced|error`),
`yougile_task_id` and `yougile_error`. **Honesty:** an invalid key yields
`status=error` with the real YouGile HTTP error — never a fake `synced`. The local
board stays the source of truth; a failed YouGile move is recorded as `error` and
is retryable via `sync-yougile` rather than rolled back.

## Telemost bot mode

Two audio source modes are supported. Backend treats both identically — only the `source` field differs.

```
1. Desktop agent mode:
   local C++ app records mic/loopback audio and uploads it.
   source = "desktop_agent"

2. Telemost bot mode:
   backend creates a bot session for a Telemost meeting URL.
   Bot joins meeting → captures audio → POST /api/audio/upload with source=telemost_bot.
   Current implementation: mock/session-based (no real browser).
   Real Playwright joiner is hook-ready in telemost_worker/mock_worker.py.
   source = "telemost_bot"
```

> **Note:** Telemost bot worker is demo/session-based.
> Real browser joiner hook is prepared but not enabled by default (`TELEMOST_WORKER_MODE=mock`).

### Telemost bot endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/telemost/join` | Start bot session, creates meeting immediately |
| GET | `/api/telemost/{bot_session_id}/status` | Get session status |
| POST | `/api/telemost/{bot_session_id}/leave` | Stop bot session |

### Bot session statuses

`created` → `joining` → `joined` → `recording` → `uploading` → `uploaded` → `left` | `error`

### Curl smoke tests

```bash
# Health
curl http://localhost:8000/api/health

# Join Telemost meeting
curl -X POST http://localhost:8000/api/telemost/join \
  -H "Content-Type: application/json" \
  -d '{"meeting_url":"https://telemost.yandex.ru/j/demo","meeting_id":"demo-telemost"}'

# Check bot status  (replace bot_session_id with value from join response)
curl http://localhost:8000/api/telemost/bot_abc123def456/status

# Upload audio as Telemost bot
curl -X POST http://localhost:8000/api/audio/upload \
  -F "audio=@rec.wav" \
  -F "agent_id=telemost_bot" \
  -F "meeting_id=demo-telemost" \
  -F "source=telemost_bot" \
  -F "started_at=2026-06-04T12:00:00Z" \
  -F "ended_at=2026-06-04T12:01:00Z"

# List meetings (both sources appear here)
curl http://localhost:8000/api/meetings

# Leave meeting
curl -X POST http://localhost:8000/api/telemost/bot_abc123def456/leave
```

Allowed `source` values: `desktop_agent`, `telemost_bot`. Unknown values return 400.

### Environment variables for Telemost bot

```env
TELEMOST_WORKER_MODE=mock         # mock (default) | playwright
TELEMOST_BOT_NAME="Grey Cardinal Bot"
TELEMOST_JOIN_TIMEOUT_SEC=60
TELEMOST_MAX_MEETING_MINUTES=120
```

### Real Telemost bot — implementation plan

When ready to plug in a real browser joiner, implement `PlaywrightTelemostBotWorker` in
`apps/brain-api/src/brain_api/telemost_worker/playwright_worker.py` and set `TELEMOST_WORKER_MODE=playwright`.

Steps the real worker must perform:

```
1. pip install 'brain-api[telemost]'  # includes playwright
2. playwright install chromium
3. Launch Chromium via async_playwright()
4. Navigate to meeting_url
5. Handle "Continue in browser" prompt if shown
6. Set participant name to TELEMOST_BOT_NAME
7. Mute camera, grant microphone permissions
8. Join the meeting
9. Start recording tab audio (via MediaRecorder or audio sink)
10. On stop_session(): finalize WAV file
11. POST /api/audio/upload:
      audio      = <wav file>
      agent_id   = telemost_bot
      meeting_id = <from session>
      source     = telemost_bot
      started_at / ended_at
12. Update bot session status to "uploaded"
```

The hook point is `MockTelemostBotWorker.start_session()` in `telemost_worker/mock_worker.py`
(see comments in the file). The rest of the pipeline (storage, status, frontend) is already wired.

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
