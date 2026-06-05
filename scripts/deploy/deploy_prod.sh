#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${PROD_PATH:-/opt/grey-cardinal}"
COMPOSE_FILE="docker-compose.prod.yml"

cd "$APP_DIR"

echo "Fetching main..."
git fetch origin main
git reset --hard origin/main

echo "Checking env..."
if [[ ! -f .env.production && ! -f .env ]]; then
  echo "Missing .env.production or .env" >&2
  exit 1
fi
if [[ ! -f .env.production && -f .env ]]; then
  cp .env .env.production
fi

echo "Building images..."
docker compose -f "$COMPOSE_FILE" build

echo "Starting infrastructure..."
docker compose -f "$COMPOSE_FILE" up -d postgres ollama asr-service tg-proxy

echo "Running migrations..."
docker compose -f "$COMPOSE_FILE" run --rm brain-api alembic upgrade head

echo "Starting app stack..."
docker compose -f "$COMPOSE_FILE" up -d brain-api telegram-bot audio-worker frontend caddy

echo "Pruning old dangling images..."
docker image prune -f

echo "Health checks..."
sleep 5
curl -fsS https://fishingteam.su/health
curl -fsS https://api.fishingteam.su/ready

echo "Deploy complete"
