<div align="center">

<img src="./docs/assets/misa-amane-roses.gif" alt="Misa Amane roses anime vibe" width="680" />

<br/>

<img src="./docs/assets/giphy.gif" alt="Grey Cardinal anime gif" width="520" />

# 🩸 Grey Cardinal 🖤

### AI meeting agent with a dark anime soul

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11+-111111?style=for-the-badge&logo=python&logoColor=ff003c">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Backend-111111?style=for-the-badge&logo=fastapi&logoColor=ff003c">
  <img alt="React" src="https://img.shields.io/badge/React-Dashboard-111111?style=for-the-badge&logo=react&logoColor=ff003c">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-Storage-111111?style=for-the-badge&logo=postgresql&logoColor=ff003c">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-Ready-111111?style=for-the-badge&logo=docker&logoColor=ff003c">
</p>

> **Grey Cardinal** records meeting audio, processes conversations, extracts tasks, and helps turn chaotic meetings into a clean task board.

</div>

---

## ✦ About

**Grey Cardinal** is an AI meeting assistant built for capturing audio from meetings, processing it through a backend pipeline, and turning conversations into structured tasks.

It can work with:

- 🖥️ **Desktop Agent** — Windows C++ app for microphone / loopback recording
- 🧠 **Brain API** — FastAPI backend for audio upload, meetings, tasks and integrations
- 🎧 **Audio Worker** — processing layer for uploaded audio
- 📋 **Task Board** — local board with `todo`, `in_progress`, and `done`
- 🤖 **Telegram Bot** — task management through Telegram
- 🌐 **React Dashboard** — frontend UI for meetings and tasks
- 🔗 **YouGile Integration** — optional real task sync
- 📞 **Telemost Bot Mode** — mock/session-based meeting bot flow with a hook for real Playwright implementation

---

## 🖤 Architecture

```txt
Desktop Agent / Telemost Bot
        │
        │ records audio
        ▼
POST /api/audio/upload
        │
        ▼
Brain API ───────────────► PostgreSQL
 FastAPI                    meeting + task storage
        │
        ├──► task proposal pipeline
        ├──► local board
        ├──► YouGile sync
        └──► dashboard events

React Dashboard
        ▲
        ├── GET /api/meetings
        ├── GET /api/tasks
        └── WebSocket /ws/events
```

---

## 🩸 Services

| Service | Port | Description |
|---|---:|---|
| `brain-api` | `8000` | Main FastAPI backend |
| `telegram-bot` | `8010` | Telegram task bot |
| `audio-worker` | `8020` | Audio processing worker |
| `frontend` | `5173` | React dashboard |
| `postgres` | `5432` | Database |

---

## 🚀 Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Open the dashboard:

```txt
http://localhost:5173
```

Backend health check:

```bash
curl http://localhost:8000/api/health
```

Expected response:

```json
{
  "ok": true,
  "service": "backend",
  "status": "running"
}
```

---

## 🧠 Brain Pipeline

Grey Cardinal can turn messages or transcripts into task proposals.

```txt
message / transcript
        ↓
rule-based extractor
        ↓
pending task proposal
        ↓
explicit confirmation
        ↓
real task on board
```

No fake tasks.  
No fake transcription.  
No silent integration errors.

Grey Cardinal keeps the local board as the source of truth and exposes real status for every step of the pipeline.

---

## 📡 Public API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/audio/upload` | Upload WAV audio |
| `GET` | `/api/meetings` | List meetings |
| `GET` | `/api/meetings/{id}` | Meeting details |
| `GET` | `/api/meetings/{id}/status` | Meeting status |
| `GET` | `/api/meetings/{id}/tasks` | Meeting tasks |
| `POST` | `/api/chat/messages` | Create task proposal from chat |
| `GET` | `/api/task-proposals` | List task proposals |
| `POST` | `/api/task-proposals/{id}/confirm` | Confirm proposal into task |
| `POST` | `/api/task-proposals/{id}/reject` | Reject proposal |
| `GET` | `/api/tasks` | List tasks |
| `GET` | `/api/board` | Get board columns |
| `POST` | `/api/tasks/{id}/move` | Move task |
| `GET` | `/api/digest/evening` | Evening digest |

---

## 🎙️ Upload Audio Example

```bash
curl -X POST http://localhost:8000/api/audio/upload \
  -F "audio=@recording.wav;type=audio/wav" \
  -F "agent_id=agent-001" \
  -F "meeting_id=my-meeting-123" \
  -F "source=desktop_agent" \
  -F "started_at=2026-06-03T10:00:00Z" \
  -F "ended_at=2026-06-03T10:05:00Z"
```

Example response:

```json
{
  "ok": true,
  "audio_id": "audio_a1b2c3d4e5f6",
  "meeting_id": "my-meeting-123",
  "status": "uploaded",
  "message": "Audio uploaded successfully"
}
```

---

## 🖥️ Desktop Agent

The Windows desktop agent captures microphone / loopback audio and uploads it to the backend.

### Build

```bash
cd native/desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

### Run

```bash
./build/Release/grey-cardinal-agent.exe \
  --backend http://localhost:8000 \
  --agent-id agent-001
```

Record for 60 seconds:

```bash
./build/Release/grey-cardinal-agent.exe --duration-sec 60
```

List devices:

```bash
./build/Release/grey-cardinal-agent.exe --list-devices
```

Dry run:

```bash
./build/Release/grey-cardinal-agent.exe --duration-sec 10 --dry-run
```

---

## 📞 Telemost Bot Mode

Grey Cardinal supports two audio sources:

| Source | Description |
|---|---|
| `desktop_agent` | Local desktop recorder |
| `telemost_bot` | Telemost bot session flow |

Start a Telemost bot session:

```bash
curl -X POST http://localhost:8000/api/telemost/join \
  -H "Content-Type: application/json" \
  -d '{"meeting_url":"https://telemost.yandex.ru/j/demo","meeting_id":"demo-telemost"}'
```

Check status:

```bash
curl http://localhost:8000/api/telemost/{bot_session_id}/status
```

Leave meeting:

```bash
curl -X POST http://localhost:8000/api/telemost/{bot_session_id}/leave
```

Current mode is mock/session-based.  
A real Playwright browser joiner can be plugged in later through the prepared worker hook.

---

## 🔗 YouGile Integration

Grey Cardinal can sync confirmed tasks to YouGile when enabled.

```env
YOUGILE_ENABLED=true
YOUGILE_API_BASE_URL=https://yougile.com/api-v2
YOUGILE_RATE_LIMIT_PER_MINUTE=50
YOUGILE_DISCOVERY_SCHEDULE_HOURS=6
```

Check integration status:

```bash
curl http://localhost:8000/api/integrations/yougile/status
```

| Mode | Description |
|---|---|
| Local board | Default mode, tasks stay inside Grey Cardinal |
| Real YouGile | Confirmed tasks sync to configured YouGile columns |

---

## 🌑 Frontend Dashboard

```bash
cd apps/frontend
npm install
npm run dev
```

Default dashboard URL:

```txt
http://localhost:5173
```

Set backend URL if needed:

```env
VITE_API_BASE_URL=http://localhost:8000
```

---

## 🧪 Tests

### Backend API tests

```bash
cd apps/brain-api
pip install -e .[dev]
pip install python-multipart
pytest tests/test_public_api.py tests/test_telemost.py -v
```

### Full backend tests with PostgreSQL

```bash
docker compose up postgres -d
pytest apps/brain-api/tests/ -v
```

### Desktop agent tests

```bash
cd native/desktop-agent
cmake -S . -B build -DBUILD_TESTING=ON
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
```

---

## 🗂️ Project Structure

```txt
grey-cardinal/
├── apps/
│   ├── brain-api/
│   └── frontend/
├── native/
│   └── desktop-agent/
├── packages/
│   └── contracts/
├── scripts/
├── docs/
├── docker-compose.yml
├── docker-compose.prod.yml
├── Makefile
└── README.md
```

---

## 🩸 Environment

Start from the example file:

```bash
cp .env.example .env
```

Common variables:

```env
INTERNAL_API_TOKEN=
TELEGRAM_BOT_TOKEN=
VITE_API_BASE_URL=http://localhost:8000

TELEMOST_WORKER_MODE=mock
TELEMOST_BOT_NAME="Grey Cardinal Bot"
TELEMOST_JOIN_TIMEOUT_SEC=60
TELEMOST_MAX_MEETING_MINUTES=120

YOUGILE_ENABLED=false
YOUGILE_API_BASE_URL=https://yougile.com/api-v2
```

---

## 🖤 Philosophy

Grey Cardinal is built around honesty.

It should not invent transcripts.  
It should not fake synced tasks.  
It should not silently hide integration errors.  

Instead, it keeps the local board as the source of truth and exposes real status for every step of the pipeline.

---

<div align="center">

### 🩸 Grey Cardinal

**record → understand → propose → confirm → execute**

<sub>dark meetings deserve sharp memory.</sub>

</div>
