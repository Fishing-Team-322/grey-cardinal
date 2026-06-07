# Agent Recommendations

Agent Recommendations - список действий, которые PM-агент предлагает руководителю.

Endpoints:
- `GET /api/teams/{teamId}/recommendations`
- `GET /api/companies/{companyId}/recommendations`
- `POST /api/recommendations/{id}/ignore`
- `POST /api/recommendations/{id}/apply`

Сейчас формируются рекомендации:
- просроченная задача;
- нет свежего статуса;
- задача на отсутствующем сотруднике;
- YouGile sync error/conflict.

UI:
- правый sidebar на Grey Board;
- отдельный route `/app/teams/:teamId/recommendations`.
