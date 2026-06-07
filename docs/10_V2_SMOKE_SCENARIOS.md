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

## LLM semantic parser (Groq primary / OpenRouter fallback)

Подробности — в [04_LLM_PROVIDERS.md](04_LLM_PROVIDERS.md).

### Health-check выбранного провайдера

```bash
# из браузера/кабинета: команда -> настройки -> «Проверить LLM»
# или напрямую (нужна cookie-сессия manager/director):
curl -s --cookie "gc_session=..." \
  https://fishingteam.su/api/teams/<TEAM_ID>/llm/health | jq
```

Ожидаем `status: ok`, заполненный `primary` (provider/base_url/model/latency_ms)
и `fallback` (enabled + status). Секреты в ответе отсутствуют.

### Eval русских сообщений

```bash
# Groq primary — сравнить несколько моделей
GROQ_API_KEY=gsk_... python scripts/eval/semantic_llm_eval.py \
  --provider groq \
  --models llama-3.3-70b-versatile qwen/qwen3-32b llama-3.1-8b-instant

# OpenRouter fallback
OPENROUTER_API_KEY=sk-or-... python scripts/eval/semantic_llm_eval.py \
  --provider openrouter --models deepseek/deepseek-chat-v3:free
```

Скрипт печатает `model / provider / total / accuracy / valid_json_rate /
p50_latency_ms / p95_latency_ms / errors / 429_count / timeout_count`.

### Сквозной чек в Telegram

1. Привязать чат команды (manager: «Командный Telegram»).
2. Отправить «Петя, подготовь оплату до четверга» → бот предлагает задачу.
3. Отправить «ок» → отсекается NoisePreFilter, бот молчит (kind=noise).
4. Отправить «давайте завтра созвонимся в 18:00» → предложение созвона.
