# YouGile Full Sync

Grey Cardinal хранит полноценную модель YouGile, а не только external card id.

Новые таблицы:
- `yougile_connections`
- `yougile_workspaces`
- `yougile_projects`
- `yougile_boards`
- `yougile_columns`
- `external_task_links`
- `sync_events`

Flow руководителя:
1. Открыть `/app/teams/:teamId/yougile`.
2. Подключить YouGile credentials или API key.
3. Backend проверяет connection и загружает проекты, доски, колонки, users.
4. Руководитель выбирает реальную YouGile board.
5. Система авто-мапит колонки на `backlog/todo/in_progress/blocked/review/done`, mapping можно передать API.
6. `POST /api/teams/{teamId}/yougile/import` импортирует все задачи выбранной board.
7. `POST /api/teams/{teamId}/yougile/sync` делает manual sync в обе стороны.

Конфликты:
- если локальная задача изменилась после последнего sync и YouGile тоже прислал отличающуюся версию, `external_task_links.sync_status = conflict`;
- в AI Inbox создается item `sync_conflict`;
- UI показывает conflict на карточке Grey Board.

Важное уточнение по реальному API:
официальная документация YouGile REST API v2 подтверждает `/api-v2`, bearer key, projects, boards, columns, tasks, users, webhooks. Точные поля некоторых task payload (`assigned`, `deadline`, external URL) нужно финально сверить на реальном аккаунте и при необходимости адаптировать parser в `YouGileFullSyncService`.
