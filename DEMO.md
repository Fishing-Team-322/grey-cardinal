# Grey Cardinal — Demo smoke test

End-to-end hackathon demo. The backend is autonomous (no PostgreSQL required):
the demo brain pipeline and the public audio/telemost API use a file-backed store.

## Start the backend

```bash
cd apps/brain-api
pip install -e ".[dev]"           # or: pip install fastapi uvicorn pydantic pydantic-settings python-multipart aiosqlite
# Run from the repo root so brain_api + contracts are importable:
cd ../..
PYTHONPATH="packages/contracts/python:apps/brain-api/src" \
  DATABASE_URL="sqlite+aiosqlite:///./demo.db" \
  UPLOADS_DIR="./.demo-uploads" \
  uvicorn brain_api.main:app --host 127.0.0.1 --port 8000
```

> Windows PowerShell: set the vars with `$env:NAME="..."` before `uvicorn`.
> The backend boots without PostgreSQL — the DB engine is created lazily and the
> demo endpoints below never touch it.

> **Cyrillic note:** the examples use Russian text. On Linux/macOS/WSL/Git Bash
> curl sends UTF-8 as-is. On native Windows `cmd`/PowerShell run `chcp 65001`
> first, or POST a UTF-8 JSON file with `--data-binary @body.json`.

---

## Scenario A — Chat message → proposal → board

```bash
# 1. Health
curl http://localhost:8000/api/health

# 2. Send a chat message (real rule-based extraction, no LLM required)
curl -X POST http://localhost:8000/api/chat/messages \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"demo","message_id":"msg-1","author":"Денис","text":"Нужно оплатить сервер до четверга, ответственный Иван"}'
# → {"ok":true,"has_task":true,"proposal":{"proposal_id":"proposal_xxx","status":"pending","title":"Оплатить сервер","assignee":"Иван","deadline":"до четверга",...}}

# 3. List pending proposals
curl "http://localhost:8000/api/task-proposals?status=pending"

# 4. Confirm the proposal → creates a task in the board "To do" column
curl -X POST http://localhost:8000/api/task-proposals/<proposal_id>/confirm

# 5. Board (confirmed task is now in "todo")
curl http://localhost:8000/api/board

# 5b. Move the task across statuses
curl -X POST http://localhost:8000/api/tasks/<task_id>/move \
  -H "Content-Type: application/json" -d '{"status":"in_progress"}'
```

A message with no task (e.g. `"Спасибо за встречу"`) returns `has_task=false` and
creates **no** proposal. Sending the same task twice returns `duplicate=true`.

---

## Scenario B — Audio / manual transcript

```bash
# 6. Upload audio as the desktop agent (same endpoint both sources use)
curl -X POST http://localhost:8000/api/audio/upload \
  -F "audio=@rec.wav" \
  -F "agent_id=desktop-agent" \
  -F "meeting_id=demo-meeting" \
  -F "source=desktop_agent"

# Real speech-to-text is not configured → transcript is honestly "unavailable":
curl http://localhost:8000/api/meetings/demo-meeting/transcript
# → {"transcription_status":"unavailable","reason":"STT provider is not configured"}

# 7. Inject a manual/demo transcript → runs the SAME extractor → proposal
curl -X POST http://localhost:8000/api/meetings/demo-meeting/transcript \
  -H "Content-Type: application/json" \
  -d '{"text":"Маша подготовит отчёт к пятнице","speaker":"Денис"}'
# → {"ok":true,"has_task":true,"proposal":{...,"source":"meeting_transcript"}}

# Confirm it the same way as a chat proposal:
curl -X POST http://localhost:8000/api/task-proposals/<proposal_id>/confirm
```

This is **manual transcript input**, not fake transcription. No STT provider is
faked; when one is configured later it plugs in front of the same extractor.

---

## Scenario C — Telemost bot session

```bash
# 8. Join a Telemost meeting (creates a bot session + a meeting, source=telemost_bot)
curl -X POST http://localhost:8000/api/telemost/join \
  -H "Content-Type: application/json" \
  -d '{"meeting_url":"https://telemost.yandex.ru/j/demo","meeting_id":"demo-telemost"}'
# → {"ok":true,"bot_session_id":"bot_xxx","meeting_id":"demo-telemost","status":"joining"}

# Status (honest mock/session state — the bot does NOT really join in mock mode)
curl http://localhost:8000/api/telemost/<bot_session_id>/status

# Meeting is visible in the shared meetings list with source=telemost_bot
curl http://localhost:8000/api/meetings

# 9. Leave
curl -X POST http://localhost:8000/api/telemost/<bot_session_id>/leave
# → {"ok":true,"status":"left"}
```

> **Telemost bot worker is demo/session-based.** Real browser joiner hook is
> prepared in `telemost_worker/mock_worker.py` but not enabled by default
> (`TELEMOST_WORKER_MODE=mock`). It does **not** fabricate audio or tasks.

---

## 10. Evening digest (built from real proposals/tasks)

```bash
curl http://localhost:8000/api/digest/evening
# → {"ok":true,"date":"...","created_today":[...],"pending_proposals":[...],"by_assignee":{...}}
```

---

## Scenario D — YouGile board integration

### D1. Local board mode (no YouGile credentials)

Default. `YOUGILE_ENABLED=false` → confirmed tasks live on the local board and
the integration honestly reports `disabled`. Nothing is faked.

```bash
curl http://localhost:8000/api/integrations/yougile/status
# → {"ok":true,"enabled":false,"configured":false,"status":"disabled","reason":"YOUGILE_ENABLED is false"}
```

Confirmed tasks carry `"yougile_status":"disabled"`.

### D2. Real YouGile mode (with credentials)

Set these env vars before starting the backend, then restart:

```env
YOUGILE_ENABLED=true
YOUGILE_API_BASE_URL=https://ru.yougile.com
YOUGILE_API_KEY=<your api key>          # Authorization: Bearer <key>
YOUGILE_BOARD_ID=<board id>
YOUGILE_COLUMN_TODO_ID=<todo column id>
YOUGILE_COLUMN_IN_PROGRESS_ID=<in-progress column id>
YOUGILE_COLUMN_DONE_ID=<done column id>
# Optional: map assignee names to YouGile user ids
YOUGILE_USER_MAP={"Иван":"user_id_1","Денис":"user_id_2"}
```

```bash
# 1. Check connection (real GET /api-v2/projects under the hood)
curl http://localhost:8000/api/integrations/yougile/status
# → {"ok":true,"enabled":true,"configured":true,"status":"connected","board_id":"..."}

# 2. Verify configured columns exist on the board
curl http://localhost:8000/api/integrations/yougile/columns

# 3. Send a chat message + confirm → task is created in YouGile TODO column
curl -X POST http://localhost:8000/api/chat/messages \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"demo","text":"Нужно оплатить сервер до четверга, ответственный Иван"}'
curl -X POST http://localhost:8000/api/task-proposals/<proposal_id>/confirm
# → task has "yougile_status":"synced" and a real "yougile_task_id"

# 4. Open your YouGile board manually — the card is there, in "To do".

# 5. Move the task → it moves in YouGile too
curl -X POST http://localhost:8000/api/tasks/<task_id>/move \
  -H "Content-Type: application/json" -d '{"status":"in_progress"}'
# → "yougile_status":"synced"

# 6. If a sync failed earlier (status=error), retry manually:
curl -X POST http://localhost:8000/api/tasks/<task_id>/sync-yougile
```

**Honesty notes:**
- An invalid key returns `status=error` with the real YouGile HTTP error — never a
  fake `synced`/`yougile_task_id`.
- A failed YouGile move does **not** roll back the local move; it records
  `yougile_status=error` so it stays visible and can be retried.
- The local board is always the source of truth; YouGile is best-effort sync.

---

## What is real vs mock

| Capability | State |
|---|---|
| Chat → task extraction | **Real** (rule-based RU extractor, no LLM needed) |
| Proposals + confirm/reject | **Real** (file-backed store) |
| Board + move task | **Real** (in-memory/JSON board) |
| Digest | **Real** (computed from stored data) |
| Duplicate guard | **Real** (normalized title+assignee+deadline) |
| Audio upload (both sources) | **Real** (`/api/audio/upload`) |
| Manual transcript → proposal | **Real** (same extractor) |
| YouGile board sync | **Real** when `YOUGILE_ENABLED=true` + creds; honest `disabled` fallback otherwise |
| Speech-to-text (audio→text) | **Not configured** — honest `unavailable`, never faked |
| Telemost bot joining | **Mock/session** — honest status, no fake audio/tasks |
| LLM extractor | Optional — falls back to rule-based when unset |
