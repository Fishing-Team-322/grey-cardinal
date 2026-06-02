# Grey Cardinal / Серый кардинал

Grey Cardinal превращает сообщения Telegram и финальные реплики встреч в подтверждаемые задачи.
`brain-api` хранит lifecycle задач в PostgreSQL, а интеграция с доской по умолчанию работает
через стабильный `MockBoardGateway`.

## Архитектура P0

```text
Telegram webhook -> telegram-bot -> brain-api -> PostgreSQL -> MockBoardGateway / YouGile
audio-worker -> brain-api -> transcript -> proposal -> Telegram action
native desktop-agent -> audio-worker /audio/chunk
```

- `telegram-bot` - тонкий transport adapter Telegram.
- `audio-worker` - service-client `brain-api`; поддерживает mock transcript и WAV chunks.
- `brain-api` - единственный владелец PostgreSQL и task lifecycle.
- `frontend-dashboard` - существующий websocket-клиент; на этом этапе функционально не менялся.
- `native/desktop-agent` - дополнительный Windows WASAPI loopback-клиент для audio-worker.

Подробности: [docs/00_OVERVIEW.md](docs/00_OVERVIEW.md).

## Быстрый запуск

```bash
docker compose up -d --build postgres brain-api telegram-bot
docker compose exec brain-api alembic upgrade head
curl http://localhost:8000/health
curl http://localhost:8010/health
```

Полный профиль с `audio-worker` и существующим dashboard:

```bash
docker compose --profile full up -d --build
curl http://localhost:8020/health
```

## Проверки

```bash
make install
make test
make lint
```

Изолированная проверка в Python 3.12 Docker:

```bash
docker build -f Dockerfile.test -t grey-cardinal-test .
docker run --rm grey-cardinal-test make test
docker run --rm grey-cardinal-test make lint
```

Native audio-agent проверяется отдельно:

```bash
make test-agent
```

## Ручной smoke test

Пошаговые `curl`-команды без реального Telegram находятся в
[docs/04_P0_SMOKE_TEST.md](docs/04_P0_SMOKE_TEST.md).

Для mock transcript через `audio-worker`:

```bash
curl -X POST http://localhost:8020/mock/transcript \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: dev-internal-token" \
  -d '{"text":"Петя, подготовь оплату до завтра 18:00"}'
```

Последние transcript-события:

```bash
curl -H "X-Internal-Token: dev-internal-token" \
  http://localhost:8000/internal/audio/transcripts/recent
```

## Audio Agent

Windows capture, mock WAV и installer описаны в
[native/desktop-agent/README.md](native/desktop-agent/README.md).
