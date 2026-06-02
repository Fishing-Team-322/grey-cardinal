# Архитектура сервисов

## telegram-bot

Принимает Telegram webhook, проверяет webhook secret, нормализует update в общие contracts,
вызывает internal API `brain-api` и исполняет возвращённые Telegram actions.
Он не обращается к PostgreSQL, extractor и board adapters.

## audio-worker

Имеет `/health`, mock meeting/scenario endpoints и `/audio/chunk`. Отправляет общий
`TranscriptEvent` в `brain-api` с `X-Internal-Token`. Реальный capture выполняется
внешним native audio-agent. Worker не знает о proposal, confirmation и lifecycle задач.

## brain-api

Владеет PostgreSQL, meeting/transcript lifecycle, extraction, proposal, confirmation,
задачами, reminder/digest use cases, board adapters и websocket events.

## frontend-dashboard

Существующий клиент websocket/internal API. На P0 функционально не меняется.
