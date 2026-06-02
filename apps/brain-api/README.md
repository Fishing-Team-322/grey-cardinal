# brain-api

«Мозг» Grey Cardinal. Владеет жизненным циклом задач, LLM-экстракцией,
confirmations, reminders, board-адаптерами, websocket-событиями и единолично
пишет в PostgreSQL.

## Архитектура (слои)

```text
api/            FastAPI-маршруты (тонкие, без бизнес-логики)
application/    use cases + порты (Protocol) + рендеринг сообщений
domain/         чистые сущности, enum'ы, доменные сервисы (без внешних зависимостей)
infrastructure/ БД (SQLAlchemy), LLM, board, telegram-gateway, scheduler, events
```

Зависимости направлены внутрь: `api -> application -> domain`, инфраструктура
реализует порты `application`. Домен ничего не знает про FastAPI/SQLAlchemy/httpx.

## Запуск локально

```bash
pip install -e packages/contracts/python
pip install -e "apps/brain-api[dev]"
export DATABASE_URL=postgresql+asyncpg://grey:grey@localhost:5432/grey_cardinal
cd apps/brain-api
alembic upgrade head
uvicorn brain_api.main:app --reload --port 8000
```

## Эндпоинты

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/health` | liveness |
| GET | `/ready` | проверка БД |
| POST | `/internal/telegram/message` | приём сообщения чата |
| POST | `/internal/telegram/callback` | приём нажатия кнопки |
| POST | `/internal/telegram/command` | приём команды |
| POST | `/internal/audio/transcript` | приём transcript (P1 задел) |
| GET | `/internal/audio/transcripts/recent` | internal/dev-only список последних transcript events |
| GET | `/internal/tasks` | список активных задач |
| GET | `/internal/tasks/{id}` | задача по UUID или `GC-12` |
| WS | `/ws/events` | поток событий для dashboard |

Все `/internal/*` требуют заголовок `X-Internal-Token`.

## Тесты

```bash
pytest apps/brain-api/tests -q
```

Тесты используют SQLite in-memory (aiosqlite) и фейковые gateway'и — БД и сеть не нужны.
