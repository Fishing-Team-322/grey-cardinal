#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: scripts/ops/restore_postgres.sh /opt/grey-cardinal/backups/postgres/grey_cardinal_*.dump" >&2
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
case "$BACKUP_FILE" in
  *.dump)
    cat "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T postgres pg_restore \
      -U "${POSTGRES_USER:-grey}" \
      -d "${POSTGRES_DB:-grey_cardinal}" \
      --clean --if-exists
    ;;
  *.sql.gz)
    gzip -dc "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T postgres psql \
      -U "${POSTGRES_USER:-grey}" \
      -d "${POSTGRES_DB:-grey_cardinal}"
    ;;
  *)
    echo "Unsupported backup format: $BACKUP_FILE (expected .dump or .sql.gz)" >&2
    exit 1
    ;;
esac

echo "PostgreSQL restore completed from $BACKUP_FILE"
