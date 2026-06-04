# Grey Cardinal — Deployment Guide

Production / demo deployment of the full stack behind a single domain with
automatic HTTPS. One reverse proxy (Caddy) publishes ports 80/443; everything
else stays on the internal Docker network.

```
Browser ──HTTPS──> Caddy (80/443)
                     ├─ /                       → frontend (nginx, static SPA)
                     └─ /api /ws /desktop /health → brain-api:8000
brain-api ──> postgres:5432  (internal only)
brain-api <── telegram-bot:8010, audio-worker:8020 (internal only)
```

## 1. Server requirements

- Linux x86_64 with Docker Engine + Compose v2 (`docker compose version`).
- 2 vCPU / 2 GB RAM minimum (4 vCPU / 8 GB recommended). The default stack uses
  **mock** ASR, so no GPU and no heavy models are required.
- Open inbound ports **22** (SSH), **80**, **443** only.
- ~3 GB free disk for images + volumes.

## 2. DNS

Point your domain's **A record** at the server IP (proxy/orange-cloud **off**
if you use Cloudflare, so Let's Encrypt HTTP-01 can validate):

```
Type  Name              Value
A     fishingteam.su    85.159.231.68
```

Verify before deploying: `dig +short fishingteam.su` → server IP.

## 3. Ports / firewall

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

PostgreSQL (5432) and the app services are **not** published to the host — they
are reachable only inside the Docker network.

## 4. Prepare `.env`

```bash
cd /opt/grey-cardinal
cp .env.example .env

# Generate strong secrets (do NOT keep the dev defaults):
sed -i "s|^INTERNAL_API_TOKEN=.*|INTERNAL_API_TOKEN=$(openssl rand -hex 32)|" .env
PGPW=$(openssl rand -hex 24)
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PGPW}|" .env
sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://grey:${PGPW}@postgres:5432/grey_cardinal|" .env

# Set your domain:
sed -i "s|^DOMAIN=.*|DOMAIN=fishingteam.su|" .env
chmod 600 .env
```

Optional:
- `TELEGRAM_BOT_TOKEN=` — leave empty to run the bot in mock mode (health only).
- `LLM_API_KEY/LLM_BASE_URL/LLM_MODEL` — set all three to enable LLM task
  extraction; otherwise a heuristic extractor is used.
- `DESKTOP_AUTO_CONFIRM_PROPOSALS=true` — demo convenience: transcript proposals
  become tasks automatically. Set `false` for production.

## 5. Launch the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

`brain-api` runs `alembic upgrade head` automatically on startup, so the
database schema is created/migrated on first boot.

## 6. Health checks

```bash
# From the server (internal):
docker compose -f docker-compose.prod.yml exec brain-api \
  python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').read())"

# From anywhere (public, through Caddy + HTTPS):
curl -i https://fishingteam.su/          # 200, dashboard HTML
curl -i https://fishingteam.su/api/health # {"ok":true,"service":"backend",...}
```

## 7. Open the dashboard

<https://fishingteam.su/> — the dashboard shows the API/WS status badges, the
Telemost panel, the meetings list, and a live events log.

## 8. Connect a Telegram bot (optional)

1. Create a bot with @BotFather, copy the token.
2. `sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=<token>|" .env`
3. `docker compose -f docker-compose.prod.yml up -d telegram-bot`
4. Set the webhook to `https://fishingteam.su/` only if you also expose the
   bot's webhook path through Caddy (not enabled by default). For demo, the
   bot's `/internal/*` endpoints are used by brain-api over the internal
   network and do not need a public webhook.

## 9. Run the agent / send data

The native desktop agent (Windows C++) and the Tauri desktop app post the same
API the simulator uses. To prove the end-to-end flow from any machine with
Python 3:

```bash
# Reads INTERNAL_API_TOKEN from the server .env if run there:
python scripts/demo_agent.py \
  --base-url https://fishingteam.su \
  --token "$(grep ^INTERNAL_API_TOKEN= .env | cut -d= -f2-)" \
  --text "Петя, подготовь оплату к четвергу"
```

This registers a device and posts a transcript line. Watch the dashboard
"Live events" panel: `transcript_line` → `task_proposed` → `task_created`
appear in real time.

### Native Windows agent

```powershell
cd native\desktop-agent
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
.\build\Release\grey-cardinal-agent.exe --backend https://fishingteam.su --agent-id agent-001
```

(The native agent uploads audio to `/api/audio/upload`; transcription on the
server is mock unless a real ASR provider is configured.)

## 10. Verify the data arrived

```bash
# Meetings created by audio uploads:
curl -s https://fishingteam.su/api/meetings | python3 -m json.tool

# Tasks/proposals for the demo identity (needs the internal token + identity
# headers printed by demo_agent.py):
curl -s -H "X-Internal-Token: <token>" \
     -H "X-GC-User-Id: <uid>" -H "X-GC-Device-Id: <did>" \
     -H "X-GC-Client-Session-Id: <sid>" \
     https://fishingteam.su/desktop/tasks | python3 -m json.tool
```

## 11. Logs

```bash
docker compose -f docker-compose.prod.yml logs --tail=200 brain-api
docker compose -f docker-compose.prod.yml logs --tail=200 caddy
docker compose -f docker-compose.prod.yml logs --tail=200 frontend
docker compose -f docker-compose.prod.yml logs --tail=200 telegram-bot
docker compose -f docker-compose.prod.yml logs --tail=200 audio-worker
```

## 12. Update the deployment

```bash
cd /opt/grey-cardinal
# pull/copy new code, then:
docker compose -f docker-compose.prod.yml up -d --build
```

## 13. Stop / start

```bash
docker compose -f docker-compose.prod.yml stop      # stop (keep data)
docker compose -f docker-compose.prod.yml up -d     # start again
docker compose -f docker-compose.prod.yml down      # remove containers (keeps named volumes)
```

⚠️ Do **not** run `down -v` unless you intend to delete the PostgreSQL data
volume (`postgres_data`).

## 14. Mock / optional parts

| Part | Status |
|------|--------|
| STT / transcription | **Mock** by default (`AUDIO_ASR_PROVIDER=mock`). Real STT via `asr-service` (faster-whisper) is opt-in and not started by the prod stack. |
| Telemost bot | **Mock** session manager (`telemost.py`) — manages state only, no real meeting joiner. |
| Telegram bot | Runs, but live messaging needs a real `TELEGRAM_BOT_TOKEN`. |
| LLM task extraction | Heuristic extractor unless `LLM_*` is configured. |
| Task board | `mock` provider unless YouGile is configured. |

## 15. Run the test suite (optional)

```bash
docker build -f Dockerfile.test -t gc-tests .
docker run --rm gc-tests          # runs pytest
```
