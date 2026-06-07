# Backup and restore

## PostgreSQL backup

Run on the production server:

```bash
cd /opt/grey-cardinal
bash scripts/ops/backup_postgres.sh
```

The script writes a compressed custom-format dump to:

```text
/opt/grey-cardinal/backups/postgres/
```

Copy backups off the server regularly.

## Upload volume backup

Back up `brain_uploads` with Docker:

```bash
docker run --rm \
  -v grey-cardinal_brain_uploads:/data:ro \
  -v /opt/grey-cardinal/backups/uploads:/backup \
  alpine tar czf /backup/brain_uploads_$(date -u +%Y%m%dT%H%M%SZ).tgz -C /data .
```

## Ollama models backup

Ollama models are optional to back up because they can be pulled again, but backing up `ollama_data` reduces recovery time:

```bash
docker run --rm \
  -v grey-cardinal_ollama_data:/data:ro \
  -v /opt/grey-cardinal/backups/ollama:/backup \
  alpine tar czf /backup/ollama_data_$(date -u +%Y%m%dT%H%M%SZ).tgz -C /data .
```

## Restore PostgreSQL

Stop the app tier before restore:

```bash
docker compose -f docker-compose.prod.yml stop brain-api telegram-bot audio-worker frontend
```

Restore:

```bash
bash scripts/ops/restore_postgres.sh /opt/grey-cardinal/backups/postgres/grey_cardinal_YYYYMMDDTHHMMSSZ.dump
```

`backup_postgres.sh` uses `pg_dump -Fc`, so `.dump` backups must be restored with `pg_restore`.
The restore script also supports legacy plain SQL gzip files ending in `.sql.gz`.

Start services and check readiness:

```bash
docker compose -f docker-compose.prod.yml up -d
curl -fsS https://api.fishingteam.su/ready
```
