# Архитектура сервисов

## telegram-bot

Принимает Telegram webhook, проверяет webhook secret, нормализует update в общие contracts,
вызывает internal API `brain-api` и исполняет возвращённые Telegram actions.
Он не обращается к PostgreSQL, extractor и board adapters.

## audio-worker

Имеет `/health`, mock meeting/scenario endpoints и `/audio/chunk`. Отправляет общий
`TranscriptEvent` в `brain-api` с `X-Internal-Token`. Реальный capture выполняется
внешним native audio-agent. Worker не знает о proposal, confirmation и lifecycle задач.
В production audio-worker больше не является источником speaker identity; это legacy/dev
путь для mock ASR и совместимости.

## brain-api

Владеет PostgreSQL, meeting/transcript lifecycle, extraction, proposal, confirmation,
задачами, reminder/digest use cases, board adapters и websocket events.
Новый desktop-first путь добавляет `/desktop/*`: device registration, client sessions,
meeting participants, authenticated microphone transcript ingest, desktop task list и
gamification state.

```text
Desktop App user microphone
  -> /desktop/transcripts
  -> brain-api
  -> meeting timeline
  -> task proposal
  -> Telegram/Desktop confirmation
  -> task lifecycle
```

Speaker identity берётся из authenticated desktop client, а не из diarization/voice guess.

## frontend-dashboard

Существующий клиент websocket/internal API. На P0 функционально не меняется.

## desktop-app

Primary participant client skeleton. Регистрирует dev identity/device, join'ит meeting,
отправляет mock microphone transcript в `/desktop/transcripts`, показывает мои задачи,
XP/level и daemon status.
