# Frontend/backend gaps

Текущий frontend уже подключен к существующим dev/internal endpoints `brain-api`.
Для полностью рабочей публичной версии сайта backend еще должен закрыть эти зоны.

## 1. Публичная авторизация

Сейчас сайт может работать только через `X-Internal-Token`, который нельзя отдавать в публичный браузерный клиент.

Нужно добавить:
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- сессии через secure cookie или access/refresh tokens
- роли workspace owner/member

## 2. Workspace API для cockpit

Сейчас cockpit читает internal endpoints:
- `GET /internal/tasks`
- `GET /internal/audio/transcripts/recent`
- `GET /internal/meetings/recent`
- `GET /internal/debug/health/dependencies`

Нужно добавить публичные workspace endpoints без internal token:
- `GET /api/workspaces/current`
- `GET /api/dashboard/summary`
- `GET /api/tasks`
- `GET /api/meetings/recent`
- `GET /api/transcripts/recent`
- `GET /api/integrations/status`

## 3. Download/release API

На сайте убраны фейковые download-кнопки, потому что backend пока не публикует сборки.

Нужно добавить:
- `GET /api/releases/daemon`
- `GET /api/releases/daemon/{platform}`
- version, changelog, file size, checksum
- signed download URL или прямую отдачу артефакта
- статус платформ: available/building/disabled

## 4. Desktop device provisioning

Есть `POST /desktop/devices/register`, но он internal/dev-oriented.

Нужно добавить публичный flow:
- workspace invite/token generation
- device enrollment без internal token
- device revoke/list endpoints
- daemon config endpoint с workspace token и API URL

## 5. WebSocket для браузерного dashboard

Сейчас `/ws/events` не требует пользовательской авторизации и не фильтрует события по workspace.

Нужно добавить:
- auth для websocket
- workspace/user scoping
- event replay/backlog после reconnect
- typed event contract для frontend

## 6. Board integration management

Backend уже умеет mock/YouGile provider, но сайту нечем управлять.

Нужно добавить:
- `GET /api/integrations/board`
- `PUT /api/integrations/board`
- проверку YouGile credentials
- список board/project/column mappings
- user-facing errors для missing config

## 7. Production CORS/config

В этом проходе добавлен dev CORS через `FRONTEND_ALLOWED_ORIGINS`.

Для production нужно:
- явно задать публичные origins
- убрать dev internal token из браузерных сценариев
- разделить internal и public API middleware
