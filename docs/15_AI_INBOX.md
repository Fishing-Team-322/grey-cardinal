# AI Inbox

AI Inbox - очередь human-in-the-loop решений агента.

Route: `/app/teams/:teamId/ai-inbox`.

Backend:
- `GET /api/teams/{teamId}/ai-inbox`
- `POST /api/ai-inbox/{itemId}/approve`
- `POST /api/ai-inbox/{itemId}/reject`
- `POST /api/ai-inbox/{itemId}/edit`
- `POST /api/ai-inbox/{itemId}/link-task`

Типы items:
- task proposal;
- meeting proposal;
- absence notice;
- daily report needing decision;
- duplicate warning;
- low-confidence parse;
- sync conflict.

На первом этапе система автоматически поднимает low-confidence task proposals и YouGile sync conflicts.
