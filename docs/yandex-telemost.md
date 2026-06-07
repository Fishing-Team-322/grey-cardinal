# Yandex Telemost integration

Create Yandex Telemost rooms straight from a Telegram group via the Grey Cardinal
bot: someone asks for a call → the bot asks which provider → on confirmation the
backend creates a real Telemost conference (official API) and posts the link back.

## 1. Create the Yandex OAuth app
1. Open <https://oauth.yandex.ru/> → **Create app**.
2. Name: `Grey Cardinal`. Platform: **Web services**.
3. **Redirect URI** (must match exactly):
   ```
   https://fishingteam.su/api/integrations/yandex-telemost/oauth/callback
   ```
4. Request these Telemost API permissions (scopes):
   - `telemost-api:conferences.create`
   - `telemost-api:conferences.read`
   - `telemost-api:conferences.update`
5. Save. Copy the **ClientID** and **Client secret**.

> The secret may have been exposed before — **rotate it** and only ever set the new
> value via env. It is never stored in git or printed in logs.

## 2. Configure env (server only)
Set these in `.env.production` on the server (see `.env.production.example`):
```env
YANDEX_TELEMOST_CLIENT_ID=<from Yandex>
YANDEX_TELEMOST_CLIENT_SECRET=<from Yandex, rotated>
YANDEX_TELEMOST_REDIRECT_URI=https://fishingteam.su/api/integrations/yandex-telemost/oauth/callback
YANDEX_TELEMOST_SCOPES=telemost-api:conferences.create telemost-api:conferences.read telemost-api:conferences.update
```
`.env*` is git-ignored; never commit real values.

## 3. Run migrations
The integration adds tables `yandex_telemost_integrations`, `yandex_oauth_states`,
`meeting_agent_join_jobs` (migration `0009_yandex_telemost`):
```bash
docker compose -f docker-compose.prod.yml run --rm brain-api alembic upgrade head
```

## 4. Connect Telemost in the cabinet
1. Sign in to Grey Cardinal as a **team manager**.
2. **Integrations → Yandex Telemost → Connect Yandex Telemost**.
3. Authorize Grey Cardinal in Yandex. You return to the cabinet showing
   **connected**. Tokens are stored encrypted (Fernet); they are never returned to
   the browser.
4. Optional: **Test create room** verifies the API works end-to-end.

Settings on that page:
- `enable_meeting_agent_auto_join` — queue the meeting agent to join (off by default).
- recording notice to chat — **always on** (consent guarantee; not switchable in MVP).
- default meeting title template, e.g. `Созвон Grey Cardinal — {telegram_chat_title}`.

## 5. Link a Telegram group to the workspace
A team manager binds the group to the team (Telegram bot settings / team settings).
The chat must be bound for room creation to work.

## 6. Use it
In the bound group, write e.g. «нужен созвон» / «давайте созвонимся» / «го телемост».
The bot replies with two buttons:
- **📹 Создать в Яндекс Телемост**
- **Другое / не сейчас**

On confirmation the backend creates a conference and posts the join link plus a
notice that the Grey Cardinal meeting agent may join for notes/tasks (if enabled).

## Security notes
- ClientSecret only from env; never logged, never in API responses or exceptions.
- OAuth uses a one-time `state` bound to user+team (CSRF protection); the callback
  rejects unknown/expired/used states.
- Access/refresh tokens are stored encrypted at rest and auto-refreshed.
- Errors are mapped: 401 → reconnect required, 403 → missing scope, 429 → back off,
  5xx → transient.

## Meeting agent / recording
The recording agent is a **separate role** from the bot. MVP does **not** auto-join
or do hidden recording: room creation enqueues a `MeetingAgentJoinJob`
(`pending`, or `queued` if auto-join is enabled) for a future worker. The chat
always gets the AI-recording notice.

## Alice "Конспект встреч"
Not used in MVP — there is no public API to fetch the Alice summary, and we do not
scrape it. See [yandex-telemost-alice-summary-spike.md](yandex-telemost-alice-summary-spike.md).

## Known follow-ups (pre-existing, not part of this feature)
A prior merge of `feature/v2-production-rebuild` left `models.py` with duplicate
ORM classes and `internal_telegram.py` with a duplicate kwarg, so the backend
could not import. These were resolved by aligning the affected models to the
alembic migrations (the YouGile board-mirror / `ai_inbox` v2 variants were never
migrated). The un-migrated v2 board-mirror + agentic-inbox features therefore have
failing tests until their migrations + code are reconciled — tracked separately;
they do not affect the Telemost flow.
