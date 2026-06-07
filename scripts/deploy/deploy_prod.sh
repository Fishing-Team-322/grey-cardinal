#!/usr/bin/env bash
# Server-side production deploy.
#
# Код синхронизируется на сервер из CI (git archive -> scp -> tar x), .env.production
# на сервере НЕ перезаписывается (исключается при распаковке). Здесь — только сборка,
# миграции и перезапуск. Никакого git pull: серверу не нужен доступ к GitHub.
set -euo pipefail

APP_DIR="${PROD_PATH:-/opt/grey-cardinal}"
COMPOSE_FILE="docker-compose.prod.yml"

cd "$APP_DIR"

echo "Checking env..."
if [[ ! -f .env.production ]]; then
  echo ".env.production is missing on the server" >&2
  exit 1
fi

echo "Validating compose config..."
docker compose -f "$COMPOSE_FILE" config >/dev/null

echo "Building images..."
docker compose -f "$COMPOSE_FILE" build

echo "Starting infrastructure..."
docker compose -f "$COMPOSE_FILE" up -d postgres ollama asr-service tg-proxy vpn-proxy

echo "Running migrations..."
docker compose -f "$COMPOSE_FILE" run --rm brain-api alembic upgrade head

echo "Starting app stack..."
docker compose -f "$COMPOSE_FILE" up -d brain-api telegram-bot audio-worker frontend caddy

# Caddyfile монтируется как volume — перезапуск, чтобы подхватить новые правила
# (в т.ч. блокировку /internal/*).
echo "Reloading Caddy..."
docker compose -f "$COMPOSE_FILE" restart caddy

echo "Pruning old dangling images..."
docker image prune -f >/dev/null 2>&1 || true

echo "Health checks..."
sleep 6
curl -fsS https://fishingteam.su/health && echo
curl -fsS https://fishingteam.su/ready && echo
echo "Deploy complete"
