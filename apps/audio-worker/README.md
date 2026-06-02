# audio-worker (P0 — каркас)

На P0 это **только каркас** будущего аудио-сервиса. Реальный захват системного
звука, ASR и VAD **не реализованы**. Цель — зафиксировать контракты и точку
входа, чтобы P1 подключался без изменения brain-api.

## Что есть на P0

* `GET /health` — healthcheck;
* `POST /mock/transcript` — отправляет тестовое transcript-событие в brain-api
  (`POST /internal/audio/transcript`), как будто это сказали на встрече;
* CLI `python -m audio_worker.main --text "..."` — то же из консоли;
* контракты в `audio_worker/contracts.py` (+ описание будущих P1-контрактов).

## Контракт transcript-события

```json
{
  "type": "transcript",
  "meeting_id": "string",
  "speaker_id": "string|null",
  "speaker_name": "string|null",
  "text": "string",
  "ts": "ISO8601",
  "is_final": true
}
```

## Проверка задела (audio -> задача)

```bash
# brain-api должен быть запущен
curl -X POST http://localhost:8020/mock/transcript \
  -H 'Content-Type: application/json' \
  -d '{"text":"Петя, подготовь макет до завтра 18:00"}'
```

brain-api сохранит transcript, опубликует websocket `transcript_line`, извлечёт
задачу и создаст proposal (отправит его в чат по умолчанию, если он есть).

## Будущее (P1)

System audio capture (virtual cable) → VAD → ASR → диаризация → `TranscriptEvent`
→ brain-api → proposal → board. См. `docs/08_NEXT_STAGES.md`.
