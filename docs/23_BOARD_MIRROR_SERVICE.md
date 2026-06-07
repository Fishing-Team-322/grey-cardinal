# Board Mirror Service

Grey Cardinal DB является operational mirror, YouGile — внешним провайдером,
Grey Board — интерфейсом над локальными задачами и состоянием синхронизации.

`external_task_links` — единственный runtime source of truth для связи task с
YouGile task. Legacy `board_cards` сохраняется только для совместимости.

`BoardMirrorService` выполняет импорт, создание, полное обновление полей, перенос,
закрытие, inbound/outbound sync и разрешение конфликтов. Каждая операция пишет
`sync_events`. При недоступном YouGile задача остаётся локальной со статусом
`local_only`, `pending_*` или `error`; повторный outbound sync обновляет существующую
карточку и не создаёт дубль.
