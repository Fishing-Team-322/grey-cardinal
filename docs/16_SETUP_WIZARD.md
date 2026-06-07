# Setup Wizard

Setup Wizard показывает, можно ли внедрить Grey Cardinal в компанию без ручного дебага.

Routes:
- `/app/setup`
- `/app/teams/:teamId/setup`

Backend:
- `GET /api/teams/{teamId}/setup/status`
- `POST /api/teams/{teamId}/setup/run-demo`

Шаги:
1. Company created
2. Team created
3. Participants
4. Telegram linked
5. YouGile connected
6. Board imported
7. LLM ready
8. Test scenario

Demo создает проверочную задачу и AI Inbox item, чтобы жюри увидело рабочий цикл.
