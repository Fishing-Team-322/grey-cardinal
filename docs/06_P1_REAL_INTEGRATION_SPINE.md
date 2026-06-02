# P1 Real Integration Spine

## Запуск backend demo

```bash
docker compose --profile backend up -d --build
docker compose exec brain-api alembic upgrade head
```

Dashboard для backend demo не требуется.

## Telegram

Настройте webhook и команды по [03_TELEGRAM_BOT.md](03_TELEGRAM_BOT.md), затем
в Telegram-чате выполните:

```text
/start
/bind_chat
/meeting_start
```

## Transcript pipeline

Preferred desktop-first path:

```bash
python scripts/smoke/desktop_microphone_flow.py
```

This registers a desktop device/session, joins `MTG-1`, posts an authenticated
microphone transcript to `/desktop/transcripts`, confirms the created proposal,
marks the task done, and checks XP.

Legacy audio-worker path:

```bash
curl -X POST http://localhost:8020/mock/transcript \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: dev-internal-token" \
  -d '{"speaker_name":"Петя","text":"Петя, подготовь оплату до завтра 18:00"}'
```

Transcript сохраняется, привязывается к активной встрече, из финальной реплики
создается proposal и уходит в привязанный Telegram-чат.

For production direction see [07_DESKTOP_FIRST_ARCHITECTURE.md](07_DESKTOP_FIRST_ARCHITECTURE.md).

## Demo scenario

Из Telegram:

```text
/demo_start
/tasks
/meeting_status
/meeting_stop
```

Через audio-worker:

```bash
curl -X POST http://localhost:8020/mock/scenario \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: dev-internal-token" \
  -d '{}'
```

## Debug

Debug endpoints доступны только при `APP_ENV=dev`:

```bash
curl -H "X-Internal-Token: dev-internal-token" \
  http://localhost:8000/internal/debug/state
curl -H "X-Internal-Token: dev-internal-token" \
  http://localhost:8000/internal/debug/health/dependencies
```

YouGile описан в [05_BOARD_ADAPTERS.md](05_BOARD_ADAPTERS.md).
