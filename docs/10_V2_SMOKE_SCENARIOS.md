# V2 smoke-сценарии

Все smoke-скрипты запускаются из корня репозитория.

## Fresh DB Alembic

```bash
TEST_DATABASE_URL=postgresql+asyncpg://grey:grey@localhost:5432/grey_cardinal_smoke \
  python scripts/smoke/alembic_fresh_db_check.py
```

Скрипт требует пустую PostgreSQL DB, выполняет `alembic upgrade head`, сверяет ORM-таблицы и делает минимальные вставки: user, company, company_admin, team, team_member.

## Director

```bash
python scripts/smoke/v2_director_scenario.py
```

Проверяет регистрацию, создание компании с timezone, создание двух команд и director overview.

## Manager

```bash
python scripts/smoke/v2_manager_scenario.py
```

Проверяет invite, настройку LLM, настройку YouGile, bind-code Telegram-чата и health/status endpoints.

## Employee

```bash
python scripts/smoke/v2_employee_scenario.py
```

Проверяет принятие invite, deep-link Telegram, статус привязки и базовую готовность employee dashboard data.

## Full flow

```bash
python scripts/smoke/v2_full_flow.py
```

Собирает цепочку director -> manager -> employee -> team settings -> Telegram bind -> semantic task message -> overview.

Makefile targets:

```bash
make smoke-alembic-fresh-db
make smoke-v2-director
make smoke-v2-manager
make smoke-v2-employee
make smoke-v2-full
```
