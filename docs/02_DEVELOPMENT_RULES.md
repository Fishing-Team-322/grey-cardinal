# Правила разработки

1. Межсервисные payload берутся из `packages/contracts`.
2. Internal endpoints проверяют `X-Internal-Token`.
3. Только `brain-api` обращается к PostgreSQL и board adapters.
4. Ошибка внешней доски не должна удалять локальную задачу.
5. Callback data имеют стабильный формат: `confirm_task:<uuid>`, `reject_task:<uuid>`,
   `edit_task:<uuid>`.
6. Реальный ASR, diarization, RAG и production orchestration не входят в P0.
