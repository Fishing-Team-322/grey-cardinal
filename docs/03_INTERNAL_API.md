# Internal API

Все endpoints ниже требуют заголовок:

```text
X-Internal-Token: dev-internal-token
```

## brain-api

```text
POST /internal/telegram/message
POST /internal/telegram/callback
POST /internal/telegram/command
POST /internal/audio/transcript
GET  /internal/audio/transcripts/recent
POST /internal/meetings/start
POST /internal/meetings/{meeting_public_id}/stop
GET  /internal/meetings/{meeting_public_id}
GET  /internal/meetings/active
GET  /internal/meetings/recent
GET  /internal/debug/state
GET  /internal/debug/health/dependencies
GET  /internal/tasks
GET  /internal/tasks/{task_id}
GET  /ws/events
```

## telegram-bot

```text
POST /internal/send-message
POST /internal/edit-message
POST /internal/answer-callback
```

## audio-worker

```text
GET  /health
POST /mock/transcript
POST /mock/meeting/start
POST /mock/meeting/stop
POST /mock/scenario
POST /audio/chunk
```

`POST /internal/audio/transcript` возвращает `TranscriptIngestResponse`, а не
Telegram actions. Debug endpoints доступны только при `APP_ENV=dev`.
