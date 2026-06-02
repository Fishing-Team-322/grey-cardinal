# Board adapters

По умолчанию используется безопасный `MockBoardGateway`:

```bash
BOARD_PROVIDER=mock
```

## YouGile

Получить company ID:

```bash
curl -X POST https://ru.yougile.com/api-v2/auth/companies \
  -H "Content-Type: application/json" \
  -d '{"login":"...","password":"..."}'
```

Получить API key:

```bash
curl -X POST https://ru.yougile.com/api-v2/auth/keys \
  -H "Content-Type: application/json" \
  -d '{"login":"...","password":"...","companyId":"..."}'
```

Создайте проект, доску и колонки, затем заполните локальный `.env`:

```bash
BOARD_PROVIDER=yougile
YOUGILE_API_BASE_URL=https://ru.yougile.com
YOUGILE_API_KEY=...
YOUGILE_COMPANY_ID=...
YOUGILE_PROJECT_ID=...
YOUGILE_BOARD_ID=...
YOUGILE_COLUMN_BACKLOG_ID=...
YOUGILE_COLUMN_TODO_ID=...
YOUGILE_COLUMN_IN_PROGRESS_ID=...
YOUGILE_COLUMN_REVIEW_ID=...
YOUGILE_COLUMN_BLOCKED_ID=...
YOUGILE_COLUMN_DONE_ID=...
```

Минимально обязательны key, company, project, board и To Do column. Остальные
колонки нужны для перемещений. Smoke создает реальную тестовую карточку:

```bash
YOUGILE_SMOKE_CONFIRM=1 make yougile-smoke
```
