#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: scripts/ops/restore_postgres.sh /opt/grey-cardinal/backups/dump.sql.gz" >&2
  exit 1
fi

BACKUP_FILE="$1"
APP_DIR="${PROD_PATH:-/opt/grey-cardinal}"
COMPOSE_FILE="$APP_DIR/docker-compose.prod.yml"

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

cd "$APP_DIR"
gzip -dc "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T postgres psql \
  -U "${POSTGRES_USER:-grey}" \
  -d "${POSTGRES_DB:-grey_cardinal}"

echo "PostgreSQL restore completed from $BACKUP_FILE"
