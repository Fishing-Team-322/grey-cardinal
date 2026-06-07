# LLM-провайдеры (semantic parser)

Grey Cardinal — русскоязычный сервис: бот читает Telegram-чат команды и должен
быстро и точно классифицировать каждое сообщение по `kind`:

```
task_candidate | meeting_candidate | daily_report | absence_notice |
status_update  | question          | noise         | unknown
```

## Стратегия

| Роль      | Провайдер           | Зачем                                            |
|-----------|---------------------|--------------------------------------------------|
| Primary   | **Groq** direct     | Быстрый production/demo (OpenAI-совместимый API)  |
| Fallback  | **OpenRouter**      | Подстраховка при сбое primary                    |
| Local     | **Ollama**          | Только dev / privacy mode (офлайн, без внешних API)|

Пайплайн:

```
SemanticMessageParser
  -> NoisePreFilter                      (очевидный шум не уходит в LLM)
  -> LLMProviderFactory.resolve_for_team(team_id)
  -> Primary provider  (response_format + retry на invalid JSON/schema)
  -> Fallback provider (только при сбое primary)
  -> Pydantic-валидация (SemanticParseResult, strict JSON)
  -> dict-контракт semantic_message_v2
```

Порядок резолва провайдера для команды:

1. Team-level `llm_settings` (per-team, ключ зашифрован в БД).
2. Company-level `llm_settings`.
3. Глобальные env (`LLM_*`).
4. В production — ошибка готовности, если ничего не настроено.

## Где взять Groq API key

1. Зайти на <https://console.groq.com>, войти/зарегистрироваться.
2. **API Keys → Create API Key**, скопировать ключ вида `gsk_...`.
3. Ключ — секрет. Никогда не коммитить, не логировать, хранить только в `.env`
   (на сервере `chmod 600`) или в зашифрованных per-team настройках.

## Настроить primary (Groq)

В `.env` / `.env.production`:

```ini
LLM_PROVIDER=external_api
LLM_EXTERNAL_BASE_URL=https://api.groq.com/openai/v1
LLM_EXTERNAL_API_KEY=gsk_...        # ваш ключ
LLM_MODEL=llama-3.3-70b-versatile
LLM_STRICT_JSON=true
LLM_TIMEOUT_SECONDS=8
LLM_MAX_RETRIES=2
```

## Настроить fallback (OpenRouter)

1. Ключ на <https://openrouter.ai/keys> (`sk-or-...`).
2. В `.env`:

```ini
LLM_FALLBACK_ENABLED=true
LLM_FALLBACK_PROVIDER=external_api
LLM_FALLBACK_BASE_URL=https://openrouter.ai/api/v1
LLM_FALLBACK_API_KEY=sk-or-...
LLM_FALLBACK_MODEL=deepseek/deepseek-chat-v3:free
LLM_FALLBACK_TIMEOUT_SECONDS=12
```

Fallback **включается только** если primary вернул: timeout, HTTP 429, HTTP 5xx,
невалидный JSON после ретраев, ошибку schema-валидации после ретраев, или
provider unavailable. **Валидный ответ `noise`/`unknown` сбоем не считается** и
fallback не запускает.

## Оставить Ollama local (dev/privacy)

Для офлайн-разработки или приватного режима без внешних API:

```ini
LLM_PROVIDER=local
LLM_LOCAL_BASE_URL=http://ollama:11434/v1
LLM_LOCAL_MODEL=qwen2.5:3b
LLM_TIMEOUT_SECONDS=45
```

Модель надо скачать в контейнер:

```bash
docker compose -f docker-compose.prod.yml exec ollama ollama pull qwen2.5:3b
```

> На сервере 7.8 ГБ RAM без GPU `qwen2.5:7b` не тянет (один инференс >180с).
> Для нормальной скорости используйте внешний API (Groq).

## Structured JSON (response_format)

Парсер не полагается только на промпт «верни JSON»:

1. Если модель поддерживает JSON Schema — `response_format={"type":"json_schema", ...}`.
2. Если на schema приходит HTTP 400 — мягкий downgrade на `{"type":"json_object"}`.
3. Любой ответ валидируется Pydantic-схемой `SemanticParseResult`.
4. Невалидный ответ → retry (до `LLM_MAX_RETRIES`).
5. После ретраев всё ещё невалидно → fallback.
6. Fallback тоже не справился → controlled `semantic_parse_failed`
   (задачи не создаются, чат не спамится).

## Health-check

```
GET /api/teams/{team_id}/llm/health      (роль manager/director)
```

Реально дёргает provider коротким JSON-промптом, меряет latency и проверяет
валидный JSON. Секреты (API key, Authorization) в ответ не попадают. Пример:

```json
{
  "status": "ok",
  "primary":  { "provider": "groq", "base_url": "https://api.groq.com/openai/v1",
                "model": "llama-3.3-70b-versatile", "latency_ms": 842 },
  "fallback": { "enabled": true, "provider": "openrouter",
                "model": "deepseek/deepseek-chat-v3:free", "status": "configured" }
}
```

## Eval: какая модель лучше

Набор размеченных русских сообщений: `apps/brain-api/evals/semantic_messages_ru.jsonl`
(50+ примеров на все `kind`). Скрипт прогоняет их через реальный провайдер и
печатает `accuracy / valid_json_rate / p50 / p95 latency / errors / 429 / timeout`:

```bash
# Groq, несколько моделей
GROQ_API_KEY=gsk_... python scripts/eval/semantic_llm_eval.py \
  --provider groq \
  --models llama-3.3-70b-versatile qwen/qwen3-32b llama-3.1-8b-instant

# OpenRouter (fallback-кандидаты)
OPENROUTER_API_KEY=sk-or-... python scripts/eval/semantic_llm_eval.py \
  --provider openrouter --models deepseek/deepseek-chat-v3:free

# Локальная Ollama
python scripts/eval/semantic_llm_eval.py \
  --provider ollama --models qwen2.5:3b --base-url http://localhost:11434/v1
```

Выбирайте модель с высоким `accuracy` И `valid_json_rate` при приемлемом
`p95_latency_ms`. Для бота важна и скорость (сообщения идут потоком), и точность
(меньше ложных задач). `llama-3.3-70b-versatile` — хороший баланс на Groq;
`llama-3.1-8b-instant` быстрее, но менее точен.

## Лимиты

- **Groq** free tier: ограничения по RPM/TPM и суточным токенам. При 429 включится
  fallback, но при массовом потоке лучше платный план или меньшая модель.
- **OpenRouter** `:free`-модели: жёсткие rate-limit'ы и иногда очереди — годятся как
  fallback, не как основной поток.
- `LLM_TIMEOUT_SECONDS` держите небольшим для primary (8с): бот не должен висеть.

## Почему ChatGPT Plus / Claude Pro — это НЕ backend API

Подписки **ChatGPT Plus** и **Claude Pro** дают доступ только к веб-/десктоп-чату
для человека. Это **не** programmatic API: у них нет OpenAI-совместимого
`/chat/completions`, нет API-ключа для сервера, и автоматизация через них нарушает
условия использования. Для backend нужен именно API-ключ провайдера
(Groq / OpenRouter / OpenAI API / локальная Ollama). Поэтому primary — Groq API,
а не «подписка».

## Безопасность секретов

- Ключи только через env или зашифрованные per-team настройки (`SecretCipher`).
- Никогда не логируем API key и заголовок `Authorization`
  (`redact_secret`, `redact_authorization_headers`).
- В production полный текст Telegram-сообщения в логи не пишется (только в DEBUG).
- Health-check и API-ответы ключи не возвращают.
