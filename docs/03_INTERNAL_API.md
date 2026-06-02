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
POST /audio/chunk
```
