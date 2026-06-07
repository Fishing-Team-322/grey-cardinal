# Grey Board

Grey Board - рабочий cockpit команды, а не копия Trello. Он показывает задачи вместе с источником, confidence, сигналами риска, историей агента и статусом YouGile sync.

Основной route: `/app/teams/:teamId/board`.

Режимы:
- Agent View: AI Inbox, нужно решение, активные, ждем статус, риски, готово.
- Status View: Backlog, Todo, In Progress, Blocked, Review, Done.
- People View: группировка по исполнителям.
- Risk View: просрочки, близкий дедлайн, нет статуса, sync conflicts.
- Timeline View: сегодня, завтра, неделя, без дедлайна, просрочено.
- Source View: Telegram, Telegram topic, YouGile, meeting, daily sync, manual.

Backend endpoint: `GET /api/teams/{teamId}/grey-board?view=agent`.

Карточка возвращает:
- local task fields;
- source stream;
- confidence;
- risk signals;
- agent history;
- external YouGile link and sync status.
