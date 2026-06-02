# frontend-dashboard (P0 — каркас)

Минимальный каркас Vite + React + TypeScript. На P0 это **не полноценный UI**, а
placeholder-страница «Grey Cardinal Dashboard», которая подключается к
websocket-потоку brain-api и логирует входящие события.

## Что есть

* `src/pages/DashboardPlaceholder.tsx` — placeholder с индикатором подключения и
  логом событий;
* `src/api/websocket.ts` — helper для подключения к `GET /ws/events` с авто-reconnect;
* health-видимость через статус соединения на странице.

## Запуск локально

```bash
cd apps/frontend-dashboard
npm install
npm run dev
# http://localhost:5173
```

Адрес websocket берётся из `VITE_BRAIN_WS_URL` (по умолчанию
`ws://localhost:8000/ws/events`).

## Запуск в Docker (профиль full)

```bash
docker compose --profile full up frontend-dashboard
```

## Контракты

Канонические типы событий — в `packages/contracts/typescript/src/events.ts`.
На P0 минимальная копия типов лежит в `src/api/websocket.ts`, чтобы каркас
собирался автономно. В P2 эти типы будут импортироваться из общего пакета.

## Дальше (P2)

Live theater: транскрипт встречи + карточки задач, обновляемые по websocket,
risk radar, velocity. См. `docs/08_NEXT_STAGES.md`.
