# Grey Cardinal — Полная архитектурная документация

> Составлено: 2026-06-05. Актуально для ветки `demonSSS`.

---

## Содержание

1. [Обзор системы](#1-обзор-системы)
2. [Сервер и инфраструктура](#2-сервер-и-инфраструктура)
3. [Docker-контейнеры](#3-docker-контейнеры)
4. [Нейросетевые модели](#4-нейросетевые-модели)
5. [Структура репозитория](#5-структура-репозитория)
6. [Потоки данных](#6-потоки-данных)
7. [API-эндпоинты](#7-api-эндпоинты)
8. [Конфигурация (.env)](#8-конфигурация-env)
9. [C++ Desktop Agent](#9-c-desktop-agent)
10. [Python Tray Agent](#10-python-tray-agent)

---

## 1. Обзор системы

Grey Cardinal — система автоматического извлечения задач из командных встреч.

```
Микрофоны участников
        ↓
C++ Desktop Agent (Windows)
        ↓  WAV chunks → POST /api/audio/upload
Audio Worker (Docker)
        ↓  WAV bytes → POST /transcribe
ASR Service — faster-whisper (Docker)
        ↓  текст + YandexSpeller коррекция
Brain API (Docker)
        ↓  текст → LLM-экстрактор задач
Ollama / qwen2.5:7b (Docker)
        ↓  JSON с задачей
Brain API → TaskProposal → PostgreSQL
        ↓
Telegram Bot — уведомление команде
        ↓
Пользователь подтверждает/отклоняет → YouGile карточка
```

---

## 2. Сервер и инфраструктура

| Параметр | Значение |
|----------|----------|
| IP | `85.159.231.68` |
| Домен | `fishingteam.su` |
| OS | Linux |
| CPU | Intel Xeon E5-2690 v4 @ 2.60GHz, 4 ядра |
| RAM | 7.77 GB |
| Disk | 97 GB (87 GB свободно) |
| GPU | **Нет** |
| Docker | 28.1.1 |

**Проект на сервере:** `/opt/grey-cardinal/`

**HTTPS:** Caddy 2 с автоматическим Let's Encrypt (порты 80, 443).

**Публичные URL:**

| URL | Назначение |
|-----|-----------|
| `https://fishingteam.su/` | Публичный лендинг |
| `https://fishingteam.su/#/login` | Вход |
| `https://fishingteam.su/#/register` | Регистрация |
| `https://fishingteam.su/#/app` | Рабочий кабинет (кокпит) |
| `https://fishingteam.su/api/*` | Backend API (brain-api) |
| `https://api.fishingteam.su/docs` | Swagger UI brain-api |

---

## 3. Docker-контейнеры

Все сервисы описаны в `docker-compose.prod.yml`. Запуск:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Таблица контейнеров (production)

| Контейнер | Внутренний порт | RAM (факт.) | Роль |
|-----------|----------------|-------------|------|
| `grey-cardinal-caddy-1` | **80, 443** (публичный) | ~14 MB | HTTPS reverse proxy |
| `grey-cardinal-brain-api-1` | 8000 | ~75 MB | Главный бэкенд |
| `grey-cardinal-audio-worker-1` | 8020 | ~50 MB | Приём и роутинг аудио |
| `grey-cardinal-asr-service-1` | 8030 | **~530 MB** | Speech-to-Text (Whisper) |
| `grey-cardinal-telegram-bot-1` | 8010 | ~55 MB | Telegram-бот |
| `grey-cardinal-frontend-1` | 5173 | ~12 MB | Статический фронтенд |
| `grey-cardinal-postgres-1` | 5432 (внутр.) | ~28 MB | База данных PostgreSQL 16 |
| `grey-cardinal-tg-proxy-1` | 8888 | ~3 MB | HTTP-прокси для Telegram API |
| `ollama-test` | 11434 | ~72 MB idle / **~4.5 GB активно** | LLM-сервер (qwen2.5:7b) |

> **Примечание:** `ollama-test` — вне docker-compose, запущен отдельно через `docker run`.
> Подключён к внутренней сети: `docker network connect grey-cardinal_default ollama-test`.

### Healthchecks

- `brain-api`: `GET /health` каждые 10 сек
- `asr-service`: `GET /health` каждые 10 сек (start_period: 60s — модель грузится)
- `telegram-bot`: `GET /health` каждые 10 сек
- `postgres`: `pg_isready` каждые 5 сек

---

## 4. Нейросетевые модели

### 4.1 faster-whisper (ASR / Speech-to-Text)

**Контейнер:** `grey-cardinal-asr-service-1`  
**Файл:** `apps/asr-service/main.py`  
**Dockerfile:** `apps/asr-service/Dockerfile`

| Параметр | Значение (на сервере) |
|----------|-----------------------|
| Библиотека | `faster-whisper >= 1.0.0` |
| Бэкенд | CTranslate2 (оптимизированный inference) |
| Модель | **`small`** (244 MB файл, ~530 MB RAM) |
| Устройство | CPU (int8 квантизация) |
| Язык | `ru` (русский, фиксированный) |
| YandexSpeller | **включён** (пост-коррекция текста) |
| Domain prompt | "Совещание проектной команды. Участники: Петя, Аня, Дима..." |

**Модели Whisper (иерархия по качеству):**

| Модель | Размер файла | RAM | Скорость на CPU | Качество RU |
|--------|-------------|-----|-----------------|-------------|
| `tiny` | 39 MB | ~200 MB | очень быстро | низкое |
| `base` | 74 MB | ~350 MB | быстро | среднее |
| `small` | **244 MB** | **~530 MB** | ✅ умеренно | **хорошее** |
| `medium` | 769 MB | ~1.5 GB | медленно | очень хорошее |
| `large-v3` | 1.5 GB | ~3 GB | очень медленно | отличное |

**Упоминания в репозитории:**
- `apps/asr-service/Dockerfile` — скачивает модель при build: `RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', ...)"`
- `apps/asr-service/requirements.txt` — `faster-whisper>=1.0.0`
- `apps/asr-service/main.py` — основной HTTP-сервер с `/transcribe` и `/health`
- `apps/audio-worker/src/audio_worker/asr.py` — `FasterWhisperAsrEngine` (локальный режим), `HttpAsrEngine` (делегирует в asr-service)
- `apps/audio-worker/requirements.txt` — `faster-whisper==1.2.1` (для локального dev)
- `docker-compose.prod.yml` — сервис `asr-service`, переменная `WHISPER_MODEL`
- `.env.example` — `WHISPER_MODEL=base`, `WHISPER_LANGUAGE=ru`

**Параметры запуска ASR:**

```python
segments, info = model.transcribe(
    tmp_path,
    language="ru",
    beam_size=5,
    best_of=5,
    vad_filter=True,           # фильтрует тишину
    vad_parameters={"min_silence_duration_ms": 300},
    condition_on_previous_text=False,
    initial_prompt=WHISPER_PROMPT,  # domain vocabulary hint
)
```

**YandexSpeller пост-коррекция:**

Бесплатный HTTP API `https://speller.yandex.net/services/spellservice.json/checkText`. Вызывается после Whisper, исправляет опечатки и ошибки распознавания. Timeout: 5 сек, не блокирует ответ при недоступности.

---

### 4.2 qwen2.5:7b через Ollama (LLM / Task Extraction)

**Контейнер:** `ollama-test` (standalone Docker, вне compose)  
**Образ:** `ollama/ollama:latest`  
**Внутренний порт:** `11434`

| Параметр | Значение |
|----------|--------------------|
| Модель | **`qwen2.5:7b`** |
| Размер файла | 4.7 GB |
| Квантизация | Q4 (по умолчанию Ollama) |
| RAM активный inference | **~4.5 GB** |
| RAM idle | ~72 MB |
| Скорость (4 CPU Xeon) | ~4–6 tok/s |
| Время ответа на запрос | ~30–60 сек |
| Язык | Русский + English (мультиязычная) |

**Для чего используется:**

Извлечение задач из транскриптов командных встреч. Принимает реплику (+ контекст последних 7 реплик) и возвращает JSON:

```json
{
  "has_task": true,
  "title": "Проверить интеграцию с YouGile",
  "assignee": "Аня",
  "deadline": "2026-06-07T18:00:00+03:00",
  "priority": "medium",
  "confidence": 0.92,
  "reason": "прямое поручение с дедлайном"
}
```

**Упоминания в репозитории:**
- `apps/brain-api/src/brain_api/infrastructure/llm/client.py` — `OpenAICompatibleClient` (OpenAI-совместимый HTTP-клиент, работает с Ollama)
- `apps/brain-api/src/brain_api/infrastructure/llm/extractor.py` — `LLMTaskExtractor` с fallback на эвристику
- `apps/brain-api/src/brain_api/infrastructure/llm/heuristic_extractor.py` — резервный rule-based экстрактор (без LLM)
- `apps/brain-api/src/brain_api/infrastructure/llm/prompts.py` — system/user промпты для экстракции
- `apps/brain-api/src/brain_api/container.py` — построение `LLMTaskExtractor` при наличии `LLM_API_KEY`
- `.env.example` — `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`

**Конфигурация на сервере (`.env`):**

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://ollama-test:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5:7b
```

**Запуск Ollama на сервере:**

```bash
docker run -d \
  --name ollama-test \
  -p 11434:11434 \
  -v ollama_data:/root/.ollama \
  --restart unless-stopped \
  ollama/ollama:latest

docker network connect grey-cardinal_default ollama-test
docker exec ollama-test ollama pull qwen2.5:7b
```

**Альтернативы при недоступности Ollama:**

Система автоматически откатывается на `HeuristicTaskExtractor` — rule-based экстрактор на regex/словарях. Работает без нейросети, извлекает задачи из явных конструкций типа "Аня, сделай X до пятницы".

**Groq API (не используется — заблокирован для IP сервера):**

Ключ настроен в `.env` (`gsk_...`), но Groq блокирует российские/EU IP провайдеров. При получении нового ключа или настройке прокси:

```env
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_...
LLM_MODEL=llama-3.3-70b-versatile
LLM_PROXY=socks5://user:pass@proxy_ip:1080  # если нужен прокси
```

**Вместо Groq можно использовать Together.ai, Mistral, Fireworks** — все доступны с IP сервера (проверено).

---

### 4.3 ASR в C++ Desktop Agent (опционально)

**Файл:** `native/desktop-agent/src/asr_provider.cpp`

Агент поддерживает несколько ASR-провайдеров (конфигурируется в `config.toml`):

| Провайдер | Класс | Описание |
|-----------|-------|----------|
| `mock` | `MockAsrProvider` | Возвращает заготовленные фразы (для тестов) |
| `faster_whisper_http` | `FasterWhisperHttpProvider` | **POST WAV на ASR-сервис** (текущее использование) |
| `whisper_cli` | `WhisperCliProvider` | Вызов whisper.exe через командную строку |
| `speechkit` | `SpeechKitProvider` | Yandex SpeechKit (не реализован, заглушка) |

В production агент использует `faster_whisper_http` — отправляет WAV на `https://fishingteam.su/api/audio/upload`, audio-worker проксирует в asr-service.

---

## 5. Структура репозитория

```
grey-cardinal/
│
├── apps/
│   ├── asr-service/           # Whisper HTTP-сервер
│   │   ├── Dockerfile         # python:3.11-slim + ffmpeg + faster-whisper
│   │   ├── main.py            # FastAPI, /transcribe + /health + YandexSpeller
│   │   └── requirements.txt   # faster-whisper, fastapi, httpx
│   │
│   ├── audio-worker/          # Роутер аудио
│   │   ├── Dockerfile
│   │   ├── src/audio_worker/
│   │   │   ├── main.py        # /audio/chunk, /api/audio/upload, /transcribe, /session/current
│   │   │   ├── asr.py         # MockAsrEngine / FasterWhisperAsrEngine / HttpAsrEngine
│   │   │   ├── brain_client.py # HTTP-клиент к brain-api
│   │   │   └── config.py      # Env-конфигурация
│   │   └── start-local.ps1    # Скрипт локального запуска
│   │
│   ├── brain-api/             # Главный бэкенд
│   │   ├── Dockerfile
│   │   ├── src/brain_api/
│   │   │   ├── api/routes/    # FastAPI роутеры
│   │   │   │   ├── accounts.py        # /api/auth/*
│   │   │   │   ├── organizations.py   # /api/organizations/*
│   │   │   │   ├── agents.py          # /api/agents/*, /api/daemon/*
│   │   │   │   ├── session.py         # /api/session/current (публичный)
│   │   │   │   ├── meetings.py        # /internal/meetings/*
│   │   │   │   ├── internal_audio.py  # /internal/audio/transcript
│   │   │   │   ├── internal_telegram.py # /internal/telegram/*
│   │   │   │   ├── tasks.py           # /internal/tasks/*
│   │   │   │   └── ...
│   │   │   ├── infrastructure/
│   │   │   │   ├── llm/
│   │   │   │   │   ├── client.py           # OpenAI-совместимый HTTP-клиент (Ollama/Groq)
│   │   │   │   │   ├── extractor.py        # LLMTaskExtractor (с fallback)
│   │   │   │   │   ├── heuristic_extractor.py # Rule-based fallback
│   │   │   │   │   └── prompts.py          # Системный и пользовательский промпты
│   │   │   │   ├── db/                 # SQLAlchemy + asyncpg
│   │   │   │   └── events/             # WebSocket event publisher
│   │   │   ├── application/
│   │   │   │   ├── use_cases/
│   │   │   │   │   ├── ingest_transcript_event.py # Главный пайплайн: транскрипт → задача
│   │   │   │   │   └── ...
│   │   │   │   └── text_policy.py      # has_action_verb(), pre-filter триггеры
│   │   │   └── demo/                   # Demo pipeline (JSON-store без БД)
│   │   └── alembic/                   # Миграции БД
│   │
│   ├── telegram-bot/          # Telegram-бот
│   │   └── src/telegram_bot/
│   │       ├── main.py        # Polling / webhook
│   │       └── brain_client.py # HTTP к brain-api
│   │
│   ├── frontend/              # React/JSX статический фронтенд
│   │   ├── Dockerfile         # node:20-alpine build → caddy:2-alpine serve
│   │   ├── public/js/         # JSX исходники
│   │   │   ├── main.jsx       # Роутер (hash-based: /, /login, /register, /app)
│   │   │   ├── app-cockpit.jsx # Рабочий кабинет (1500+ строк)
│   │   │   ├── auth.jsx       # Login / Register страницы
│   │   │   ├── api-client.jsx # GCApi — HTTP-клиент к brain-api
│   │   │   ├── public-hero.jsx # Публичный лендинг
│   │   │   ├── public-sections.jsx # Секции лендинга
│   │   │   ├── i18n.jsx       # Переключалка RU/EN
│   │   │   ├── icons.jsx      # SVG иконки
│   │   │   ├── data.jsx       # Demo/mock данные
│   │   │   └── download.jsx   # Страница загрузки агента
│   │   └── scripts/build-static.mjs # Babel-сборщик
│   │
│   └── tg-proxy/              # HTTP прокси для Telegram API
│       └── Dockerfile         # Nginx / CONNECT proxy
│
├── native/
│   ├── desktop-agent/         # C++ Windows desktop agent
│   │   ├── src/
│   │   │   ├── main.cpp       # Точка входа: WASAPI → record → upload
│   │   │   ├── asr_provider.cpp # ASR провайдеры (mock, http, cli, speechkit)
│   │   │   ├── chunk_uploader.cpp # Real-time стриминг чанков
│   │   │   ├── desktop_transcript_uploader.cpp # Локальный ASR + отправка текста
│   │   │   ├── audio_recorder.cpp # WASAPI захват
│   │   │   └── http_client.cpp # WinHTTP клиент
│   │   ├── include/           # Заголовки (hpp)
│   │   ├── platform/windows/  # WASAPI реализация
│   │   ├── build/             # CMake build (Release exe)
│   │   └── installer/windows/ # Inno Setup installer (.iss)
│   │
│   └── tray-agent/            # Python Windows tray приложение
│       ├── tray_agent.py      # Системный трей, опрос /api/session/current
│       ├── requirements.txt   # pystray, Pillow
│       ├── install.bat        # pip install -r requirements.txt
│       ├── start.bat          # Запуск без окна консоли
│       └── build_exe.bat      # PyInstaller → .exe
│
├── packages/
│   └── contracts/python/      # Общие Pydantic-модели
│       └── grey_cardinal_contracts/
│           ├── transcripts.py # TranscriptEvent, TranscriptIngestResponse
│           ├── meetings.py    # MeetingStartRequest, MeetingStatusResponse
│           └── ...
│
├── scripts/
│   └── setup_yougile.py       # Интерактивная настройка YouGile интеграции
│
├── Caddyfile                  # Маршрутизация через Caddy
├── docker-compose.prod.yml    # Production состав контейнеров
├── docker-compose.yml         # Dev состав
└── .env.example               # Шаблон переменных окружения
```

---

## 6. Потоки данных

### 6.1 Голосовая встреча → Задача (основной путь)

```
1. Пользователь открывает fishinteam.su → нажимает /meeting_start в Telegram
   (или: POST /internal/meetings/start через brain-api)
   → создаётся Meeting с public_id "MTG-XXXXXX"

2. C++ Desktop Agent (grey-cardinal-agent.exe) стартует на ПК каждого участника
   → записывает микрофон 30 сек через WASAPI
   → POST multipart/form-data к https://fishingteam.su/api/audio/upload
   → Caddy проксирует на audio-worker:8020

3. audio-worker получает WAV-файл
   → GET /internal/meetings/active → получает активный MTG-XXXXXX
   → POST /transcribe на asr-service:8030 (WAV bytes)

4. asr-service (faster-whisper small, CPU int8)
   → VAD фильтрация тишины
   → Whisper transcribe с domain prompt
   → YandexSpeller пост-коррекция
   → {"text": "Аня, нужно проверить YouGile до конца недели.", "confidence": 0.93}

5. audio-worker → POST /internal/audio/transcript на brain-api:8000
   → TranscriptEvent сохраняется в PostgreSQL

6. brain-api IngestTranscriptEvent:
   → pre-filter: "Готова." / "Окей" → пропуск (экономия LLM-вызовов)
   → загружает последние 7 реплик встречи (контекстное окно)
   → LLMTaskExtractor (qwen2.5:7b через Ollama):
       system: "Ты ассистент PM..."
       user: {контекст диалога + текущая реплика}
       → {"has_task": true, "assignee": "Аня", "deadline": "...", ...}
   → fallback на HeuristicTaskExtractor если Ollama недоступна

7. TaskProposal создаётся в БД
   → telegram-bot отправляет уведомление в групповой чат
   → Пользователь нажимает "Подтвердить" → Task создаётся
   → Task синхронизируется с YouGile (если настроен)
```

### 6.2 Обнаружение активной встречи агентом (session discovery)

```
Python Tray Agent (на ПК пользователя)
    каждые 5 сек → GET https://fishingteam.su/api/session/current
    ← {"active": true, "meeting_id": "MTG-XXXXXX"}
    → запускает grey-cardinal-agent.exe --meeting-id MTG-XXXXXX --duration-sec 30
    → после завершения записи сразу запускает новый 30-сек цикл
    → повторяет пока встреча активна
```

### 6.3 Real-time streaming (альтернативный путь, `/audio/chunk`)

```
C++ ChunkUploader → POST /audio/chunk (raw WAV 5-10 сек)
    → audio-worker → asr-service → текст
    → brain-api (WebSocket публикация + LLM экстракция)
```

---

## 7. API-эндпоинты

### Публичные (без токена)

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/health` | Healthcheck brain-api |
| `GET` | `/api/session/current` | Активная командная встреча |
| `POST` | `/api/auth/register` | Регистрация |
| `POST` | `/api/auth/login` | Вход |
| `POST` | `/api/auth/logout` | Выход |
| `GET` | `/api/auth/me` | Текущий пользователь |
| `PATCH` | `/api/auth/me` | Обновить профиль |
| `GET/POST` | `/api/organizations/*` | Организации и участники |
| `GET` | `/api/agents` | Список подключённых агентов |
| `POST` | `/api/agents/pairing-code` | Код привязки агента |
| `GET` | `/api/task-proposals` | Предложения задач |
| `POST` | `/api/task-proposals/{id}/confirm` | Подтвердить задачу |
| `POST` | `/api/task-proposals/{id}/reject` | Отклонить задачу |
| `GET` | `/api/board` | Kanban-доска |
| `POST` | `/api/tasks/{id}/move` | Переместить задачу |
| `GET` | `/api/digest/evening` | Вечерний дайджест |
| `GET` | `/api/integrations/yougile/status` | Статус YouGile |
| `POST` | `/api/chat/messages` | Отправить сообщение (demo) |

### Для C++ агента (через Caddy → audio-worker)

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/audio/upload` | Загрузить WAV-запись (multipart) |
| `GET` | `/api/session/current` | Проверить активную встречу |

### Внутренние (требуют `X-Internal-Token`)

| Метод | Путь | Сервис | Описание |
|-------|------|--------|----------|
| `POST` | `/internal/audio/transcript` | brain-api | Принять транскрипт |
| `GET` | `/internal/meetings/active` | brain-api | Активная встреча |
| `POST` | `/internal/meetings/start` | brain-api | Начать встречу |
| `POST` | `/internal/meetings/{id}/stop` | brain-api | Завершить встречу |
| `GET` | `/internal/audio/transcripts/recent` | brain-api | Последние транскрипты |
| `POST` | `/transcribe` | asr-service | Транскрибировать WAV |
| `GET` | `/audio/chunk` | audio-worker | Принять стриминг-чанк |

### ASR Service (порт 8030, внутренний)

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/health` | `{"ok": true, "model": "small", "speller": true}` |
| `POST` | `/transcribe` | WAV bytes → `{"text": "...", "confidence": 0.93, "speller_applied": true}` |

---

## 8. Конфигурация (.env)

Полный шаблон: `.env.example`. Ключевые параметры:

```env
# ── Домен и CORS ─────────────────────────
DOMAIN=fishingteam.su
FRONTEND_ALLOWED_ORIGINS=https://fishingteam.su,https://api.fishingteam.su

# ── База данных ───────────────────────────
DATABASE_URL=postgresql+asyncpg://grey:PASSWORD@postgres:5432/grey_cardinal
POSTGRES_DB=grey_cardinal
POSTGRES_USER=grey
POSTGRES_PASSWORD=...

# ── Безопасность ──────────────────────────
INTERNAL_API_TOKEN=...  # Токен между сервисами (32 байта hex)
JWT_SECRET=...          # JWT для сессий пользователей
JWT_COOKIE_SECURE=true

# ── LLM (извлечение задач) ────────────────
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://ollama-test:11434/v1   # Ollama локальный
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5:7b
LLM_PROXY=                                 # socks5://... если нужен прокси для Groq

# ── ASR (речь в текст) ────────────────────
WHISPER_MODEL=small                        # tiny|base|small|medium|large-v3
WHISPER_LANGUAGE=ru
ASR_SERVICE_URL=http://asr-service:8030    # Для audio-worker → asr-service

# ── Audio Worker ──────────────────────────
AUDIO_ASR_PROVIDER=mock                    # mock|faster_whisper|http
AUDIO_FASTER_WHISPER_MODEL=base
AUDIO_WORKER_SAVE_CHUNKS=false

# ── Telegram ──────────────────────────────
TELEGRAM_BOT_TOKEN=...
TELEGRAM_USE_POLLING=true
TELEGRAM_WEBHOOK_SECRET=...

# ── YouGile ───────────────────────────────
BOARD_PROVIDER=mock                        # mock|yougile|jira
YOUGILE_ENABLED=false
YOUGILE_API_KEY=...
YOUGILE_COMPANY_ID=...
YOUGILE_PROJECT_ID=...
YOUGILE_BOARD_ID=...
YOUGILE_COLUMN_TODO_ID=...
```

---

## 9. C++ Desktop Agent

**Путь:** `native/desktop-agent/`  
**Язык:** C++17, Windows-only (WASAPI)  
**Сборка:** CMake + MSVC  
**Бинарник:** `native/desktop-agent/build/Release/grey-cardinal-agent.exe`  
**Installer:** `native/desktop-agent/installer/windows/output/GreyCardinalAgentSetup.exe`

**Запуск:**

```cmd
grey-cardinal-agent.exe --backend https://fishingteam.su --duration-sec 30 --capture-mode microphone
```

**Ключевые параметры:**

| Флаг | По умолчанию | Описание |
|------|-------------|----------|
| `--backend` | `http://127.0.0.1:8010` | URL сервера |
| `--meeting-id` | auto UUID | ID встречи |
| `--duration-sec` | 0 (до Ctrl+C) | Длина записи в секундах |
| `--capture-mode` | `microphone` | `microphone` / `system_loopback` |
| `--list-devices` | — | Показать устройства и выйти |
| `--dry-run` | false | Записать, но не загружать |
| `--config` | `%LOCALAPPDATA%\GreyCardinal\Agent\config.toml` | Путь к конфигу |

**Конфиг (`config.toml`):**

```toml
backend_url = "https://fishingteam.su"
agent_id = "desktop-agent"
meeting_id = "MTG-XXXXXX"
capture_mode = "microphone"
chunk_ms = 30000
```

**Поток данных агента:**

```
WASAPI (микрофон/loopback)
    → AudioRecorder (PCM буфер)
    → Uploader::uploadAudio()
    → POST /api/audio/upload (multipart: audio, agent_id, meeting_id, started_at, ended_at)
    → audio-worker → asr-service → brain-api
```

**ASR-провайдеры в C++ агенте** (выбирается в config.toml):

- `faster_whisper_http` — HTTP POST на asr-service (production)
- `mock` — тестовые фразы
- `whisper_cli` — локальный whisper.exe (`%WAV%` placeholder)
- `speechkit` — заглушка (не реализован)

---

## 10. Python Tray Agent

**Путь:** `native/tray-agent/tray_agent.py`  
**Язык:** Python 3.11+, Windows

**Назначение:** Висит в системном трее, автоматически запускает/останавливает запись на основе активной командной сессии.

**Установка и запуск:**

```cmd
cd native\tray-agent
install.bat          # pip install pystray pillow
start.bat            # запуск без окна консоли (pythonw)
```

**Логика работы:**

```
Запуск → системный трей (серый значок)
    каждые 5 сек → GET {server_url}/api/session/current
    
    Если active=true:
        → зелёный значок
        → запустить grey-cardinal-agent.exe с meeting_id
        → ждать завершения чанка (30 сек)
        → если встреча ещё активна → новый чанк
    
    Если active=false:
        → серый значок
        → остановить запись
```

**Конфиг** (`%LOCALAPPDATA%\GreyCardinal\Agent\tray_config.toml`, создаётся автоматически):

```toml
server_url    = "https://fishingteam.su"
agent_exe     = "C:\Program Files\Grey Cardinal Agent\grey-cardinal-agent.exe"
chunk_sec     = 30
poll_interval = 5
capture_mode  = "microphone"
```

**Иконки** (генерируются из кода через PIL, без внешних файлов):

| Цвет | Состояние |
|------|-----------|
| ⬜ Серый | Нет активной встречи |
| 🟢 Зелёный | Идёт запись |
| 🟡 Жёлтый | Подключение... |
| 🔴 Красный | Ошибка подключения |

---

## Appendix: RAM-бюджет сервера

```
Всего RAM:           7 770 MB
─────────────────────────────────────────────
asr-service:          530 MB  (Whisper small загружен)
ollama idle:           72 MB  (qwen2.5:7b выгружен)
ollama активный:    4 500 MB  (qwen2.5:7b во время inference)
brain-api:             75 MB
telegram-bot:          55 MB
audio-worker:          50 MB
postgres:              28 MB
frontend:              12 MB
caddy:                 14 MB
tg-proxy:               3 MB
─────────────────────────────────────────────
Итого idle:          ~840 MB
Итого пиковый:     ~5 340 MB
Свободно пиковый:  ~2 430 MB  ✅
```

> **Важно:** Ollama при активном inference (qwen2.5:7b) потребляет ~4.5 GB RAM.
> При параллельной работе ASR + LLM пиковое потребление ~5.3 GB, что укладывается в 7.77 GB.
> Модели **не** запускаются одновременно: ASR работает per-chunk (сек), LLM — per-utterance (30-60 сек).
