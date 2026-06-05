#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/grey-cardinal}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups/postgres}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"
cd "$APP_DIR"

DB_NAME="${POSTGRES_DB:-grey_cardinal}"
DB_USER="${POSTGRES_USER:-grey}"
OUT="$BACKUP_DIR/${DB_NAME}_${STAMP}.dump"

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$OUT"

echo "$OUT"
