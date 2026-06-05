# Deploy and rollback

Production deploy is automatic on every push to `main`.

Flow:

1. GitHub Actions connects to the production server over SSH.
2. The server runs `scripts/deploy/deploy_prod.sh`.
3. The script resets `/opt/grey-cardinal` to `origin/main`.
4. Images are built with `docker-compose.prod.yml`.
5. Infrastructure services start first: `postgres`, `ollama`, `asr-service`, `tg-proxy`.
6. Alembic migrations run once from a one-shot `brain-api` container.
7. Application services start: `brain-api`, `telegram-bot`, `audio-worker`, `frontend`, `caddy`.
8. `/health` and `/ready` are checked.

Required GitHub secrets:

- `PROD_HOST`
- `PROD_PORT`
- `PROD_USER`
- `PROD_SSH_KEY`
- `PROD_PATH`

Production environment values are not stored in git. Keep them on the server in:

```text
/opt/grey-cardinal/.env.production
```

Manual deploy:

```bash
cd /opt/grey-cardinal
bash scripts/deploy/deploy_prod.sh
```

Logs:

```bash
docker compose -f docker-compose.prod.yml logs -f brain-api
docker compose -f docker-compose.prod.yml logs -f telegram-bot
docker compose -f docker-compose.prod.yml logs -f caddy
```

Rollback to a previous commit:

```bash
cd /opt/grey-cardinal
git fetch origin
git reset --hard <commit-sha>
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
curl -fsS https://fishingteam.su/health
curl -fsS https://api.fishingteam.su/ready
```

If a migration breaks deploy:

1. Do not start multiple app containers with competing migrations.
2. Stop the app tier: `docker compose -f docker-compose.prod.yml stop brain-api telegram-bot audio-worker frontend`.
3. Restore the database from the latest dump if the migration changed data destructively.
4. Reset the repo to the last good commit.
5. Run `docker compose -f docker-compose.prod.yml run --rm brain-api alembic downgrade <revision>` only when the migration has a verified downgrade.
6. Start the app tier and re-check `/ready`.
