# Grey Cardinal / Серый кардинал

Grey Cardinal превращает сообщения Telegram и финальные реплики встреч в подтверждаемые задачи.
`brain-api` хранит lifecycle задач в PostgreSQL, а интеграция с доской по умолчанию работает
через стабильный `MockBoardGateway`.

Новая audio-архитектура — desktop-first: каждый участник ставит desktop app,
а speaker identity берётся из authenticated desktop session/device, не из voice recognition.
Production-путь для речи: `/desktop/transcripts` с `capture_mode=microphone`.

## Архитектура P1

```text
Telegram webhook -> telegram-bot -> brain-api -> PostgreSQL -> MockBoardGateway / YouGile
desktop-app microphone -> brain-api /desktop/transcripts -> meeting timeline -> proposal
audio-worker -> brain-api -> meeting -> transcript -> proposal -> Telegram action
native desktop-agent -> audio-worker /audio/chunk (system_loopback_experimental)
```

- `telegram-bot` - тонкий transport adapter Telegram.
- `audio-worker` - service-client `brain-api`; поддерживает mock meeting/scenario, transcript и WAV chunks.
- `brain-api` - единственный владелец PostgreSQL, meeting lifecycle и task lifecycle.
- `apps/desktop-app` - primary participant client skeleton: dev identity, meeting join, mock microphone transcript, tasks, XP.
- `frontend-dashboard` - существующий websocket-клиент; на этом этапе функционально не менялся.
- `native/desktop-agent` - дополнительный Windows WASAPI loopback-клиент для audio-worker, только experimental.

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

Backend demo без dashboard:

```bash
docker compose --profile backend up -d --build
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

Desktop app skeleton:

```bash
cd apps/desktop-app
npm install
npm run build
```

## Ручной smoke test

Пошаговые `curl`-команды без реального Telegram находятся в
[docs/04_P0_SMOKE_TEST.md](docs/04_P0_SMOKE_TEST.md). P1 meeting/demo flow описан в
[docs/06_P1_REAL_INTEGRATION_SPINE.md](docs/06_P1_REAL_INTEGRATION_SPINE.md).

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

Desktop-first microphone smoke:

```bash
python scripts/smoke/desktop_microphone_flow.py
```

Подробности: [docs/07_DESKTOP_FIRST_ARCHITECTURE.md](docs/07_DESKTOP_FIRST_ARCHITECTURE.md).

## Audio Agent

Windows capture, mock WAV и installer описаны в
[native/desktop-agent/README.md](native/desktop-agent/README.md).
