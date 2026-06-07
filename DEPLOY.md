# Grey Cardinal — Deployment Guide

Production / demo deployment behind one domain with automatic HTTPS. Only Caddy
publishes ports (80/443); everything else is internal.

Daemon package setup and verification are documented in
[DAEMON_SETUP.md](DAEMON_SETUP.md).

```
Browser ─HTTPS─> Caddy (80/443)
                   ├─ /                       → frontend-dashboard:5173 (static Grey Cardinal app)
                   ├─ /api /ws /desktop /health → brain-api:8000
                   └─ /webhooks/telegram        → telegram-bot:8010
brain-api ─> postgres:5432            (internal)
telegram-bot ─HTTPS_PROXY─> tg-proxy ─> api.telegram.org   (internal)
audio-worker, asr-service             (internal)
```

The Grey Cardinal app (`apps/frontend-dashboard/public`) calls the backend via
same-origin `/api` (`public/js/api-client.jsx`): chat → proposal → board → tasks.

## 1. Server requirements
- Linux x86_64, Docker Engine + Compose v2.
- 4 vCPU / 8 GB recommended (real STT model `base` runs on CPU).
- Inbound ports 22, 80, 443 only. ~4 GB disk.

## 2. DNS
A record for your domain → server IP (Cloudflare proxy **off** so Let's Encrypt
HTTP-01 validates). Verify: `dig +short fishingteam.su`.

## 3. Firewall
```bash
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
```
PostgreSQL and the app services are not published to the host.

## 4. Prepare `.env`
```bash
cd /opt/grey-cardinal
cp .env.example .env
sed -i "s|^INTERNAL_API_TOKEN=.*|INTERNAL_API_TOKEN=$(openssl rand -hex 32)|" .env
PGPW=$(openssl rand -hex 24)
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PGPW}|" .env
sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://grey:${PGPW}@postgres:5432/grey_cardinal|" .env
sed -i "s|^DOMAIN=.*|DOMAIN=fishingteam.su|" .env
chmod 600 .env
```
Optional: `TELEGRAM_BOT_TOKEN=` (enables the bot), `LLM_*` (LLM extraction),
`YOUGILE_ENABLED=true` + keys (real board sync).

## 4a. Windows tray-agent MSI (required before building `frontend`)
The Windows tray agent installer **is not stored in git** (binaries are published
out-of-band to keep the repo small). The `frontend` image bakes
`apps/frontend/public/` via `COPY public/`, so the MSI must exist at:

```
apps/frontend/public/downloads/GreyCardinalAgent-x64.msi
```

Provide it before building the `frontend` image via one of:
- **CI artifact** `grey-cardinal-agent-windows-x64` (workflow *Build Windows tray
  agent MSI*) — download and drop it into `apps/frontend/public/downloads/`.
- **Local build** (Windows, needs Python + PyInstaller and dotnet for WiX):
  ```powershell
  ./scripts/package_windows_tray_msi.ps1 -Version 0.6.5
  ```

If the file is missing, `/downloads/GreyCardinalAgent-x64.msi` serves **404** after
deploy. The deploy script (`scripts/deploy/deploy_prod.sh`) and `make docker-build`
run a guard that fails fast with a clear message before the image is built:

```bash
bash scripts/check_frontend_downloads.sh   # or: make check-frontend-downloads
```

> `apps/frontend/public/downloads/*.msi` and `*.exe` stay **git-ignored** and must
> never be committed.

## 5. Launch
```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```
`brain-api` runs `alembic upgrade head` on start.

## 6. Health / open
```bash
curl -i https://fishingteam.su/             # dashboard
curl -i https://fishingteam.su/api/health   # {"ok":true,...}
```
Open <https://fishingteam.su/> → landing → "Войти" → cockpit (Обзор / Встречи /
Задачи / Канбан / Риски).

## 7. End-to-end demo (real data in the UI)
```bash
# Send a chat message → backend extracts a proposal → auto-confirms a task → board.
curl -X POST https://fishingteam.su/api/chat/messages \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"demo","message_id":"m1","author":"Денис","text":"Нужно оплатить сервер до четверга, ответственный Иван"}'

curl https://fishingteam.su/api/task-proposals      # pending proposals
curl https://fishingteam.su/api/tasks               # tasks
curl https://fishingteam.su/api/board               # board columns
```
The cockpit (Задачи / Канбан) shows these via `/api`.

## 8. Telegram bot
1. `sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=<token>|" .env`
2. `sed -i "s|^TELEGRAM_WEBHOOK_SECRET=.*|TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 16)|" .env`
3. `docker compose -f docker-compose.prod.yml up -d tg-proxy telegram-bot`
4. Register the webhook (the bot reaches Telegram through `tg-proxy`):
```bash
TG=$(grep ^TELEGRAM_BOT_TOKEN= .env|cut -d= -f2-); WS=$(grep ^TELEGRAM_WEBHOOK_SECRET= .env|cut -d= -f2-)
docker compose -f docker-compose.prod.yml exec -T telegram-bot python -c "import os,urllib.request,urllib.parse,json; d=urllib.parse.urlencode({'url':'https://fishingteam.su/webhooks/telegram','secret_token':os.environ.get('WS','')}).encode(); print(json.load(urllib.request.urlopen('https://api.telegram.org/bot'+os.environ['TG']+'/setWebhook',data=d,timeout=15)))" 2>/dev/null
```
Then message the bot in Telegram.

### tg-proxy (why)
This host blocks Telegram's default IPs / has no IPv6 egress. `tg-proxy`
(tinyproxy) pins a reachable Telegram IP and the bot uses it via `HTTPS_PROXY`
(its http calls to brain-api go direct via `NO_PROXY`). If your host reaches
Telegram normally, you can drop `tg-proxy` and the bot's `HTTPS_PROXY`.

## 8a. Yandex Telemost (create rooms from Telegram)
Create Telemost rooms from a Telegram group via the bot. Full guide:
[docs/yandex-telemost.md](docs/yandex-telemost.md).

1. Create a Yandex OAuth app (platform Web) with redirect URI
   `https://fishingteam.su/api/integrations/yandex-telemost/oauth/callback` and scopes
   `telemost-api:conferences.create read update`.
2. Set `YANDEX_TELEMOST_CLIENT_ID` / `YANDEX_TELEMOST_CLIENT_SECRET` (rotated) in
   `.env.production` (see `.env.production.example`).
3. `docker compose -f docker-compose.prod.yml run --rm brain-api alembic upgrade head`
   (adds migration `0009_yandex_telemost`).
4. In the cabinet: **Integrations → Yandex Telemost → Connect**, then bind the
   Telegram group to the team. In the group, «нужен созвон» → bot offers to create
   the room. Tokens are stored encrypted; the secret is env-only and never logged.

## 9. Logs / update / stop
```bash
docker compose -f docker-compose.prod.yml logs --tail=200 brain-api
docker compose -f docker-compose.prod.yml up -d --build      # update
docker compose -f docker-compose.prod.yml down                # stop (keeps volumes)
```
⚠️ Do not run `down -v` — it deletes the `postgres_data` and `brain_uploads` volumes.

## 10. Mock / optional
| Part | Status |
|------|--------|
| STT | `asr-service` real (faster-whisper `base`); `audio-worker` provider = mock. |
| Telemost | Real room creation via Yandex OAuth (`YANDEX_TELEMOST_*`); the meeting-agent join worker is a stub. |
| Telegram | needs `TELEGRAM_BOT_TOKEN`; reaches Telegram via `tg-proxy`. |
| LLM | heuristic unless `LLM_*` set. |
| Board | local unless `YOUGILE_ENABLED=true` + keys. |

## 11. Tests
```bash
docker build -f Dockerfile.test -t gc-tests . && docker run --rm gc-tests
```
