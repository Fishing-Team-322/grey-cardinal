# Manual P0 smoke test

## 1. Поднять базовые сервисы

```bash
docker compose up -d --build postgres brain-api telegram-bot
docker compose exec brain-api alembic upgrade head
```

## 2. Создать proposal

```bash
curl -X POST http://localhost:8000/internal/telegram/message \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: dev-internal-token" \
  -d '{
    "update_id": 1,
    "message_id": 101,
    "chat": {"id": -100123456789, "type": "supergroup", "title": "Hackathon Team"},
    "sender": {"id": 111222333, "username": "petya", "first_name": "Петя"},
    "text": "Петя, подготовь оплату до завтра 18:00",
    "date": "2026-06-02T15:00:00+03:00",
    "raw": {}
  }'
```

Скопировать UUID из `confirm_task:<uuid>`.

## 3. Подтвердить задачу

```bash
curl -X POST http://localhost:8000/internal/telegram/callback \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: dev-internal-token" \
  -d '{
    "update_id": 2,
    "callback_query_id": "cb-1",
    "from_user": {"id": 111222333, "username": "petya", "first_name": "Петя"},
    "message": {"message_id": 102, "chat_id": -100123456789},
    "data": "confirm_task:PASTE_UUID_HERE",
    "raw": {}
  }'
```

## 4. Проверить и закрыть задачу

```bash
curl -H "X-Internal-Token: dev-internal-token" http://localhost:8000/internal/tasks
curl -X POST http://localhost:8000/internal/telegram/command \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: dev-internal-token" \
  -d '{
    "update_id": 3,
    "message_id": 103,
    "chat": {"id": -100123456789, "type": "supergroup", "title": "Hackathon Team"},
    "sender": {"id": 111222333, "username": "petya", "first_name": "Петя"},
    "command": "done",
    "args": ["GC-1"],
    "text": "/done GC-1",
    "date": "2026-06-02T15:05:00+03:00",
    "raw": {}
  }'
```

## 5. Проверить transcript flow

```bash
docker compose --profile full up -d --build audio-worker
curl -X POST http://localhost:8020/mock/transcript \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: dev-internal-token" \
  -d '{"text":"Аня, проверь интеграцию с YouGile до завтра"}'
curl -H "X-Internal-Token: dev-internal-token" \
  http://localhost:8000/internal/audio/transcripts/recent
```

Полный P1 smoke с `/bind_chat`, meeting lifecycle, demo scenario и debug state:
[06_P1_REAL_INTEGRATION_SPINE.md](06_P1_REAL_INTEGRATION_SPINE.md).
