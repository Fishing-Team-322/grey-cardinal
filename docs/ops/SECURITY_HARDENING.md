# Production security hardening

## Ollama

Ollama is part of `docker-compose.prod.yml` and is available only inside the Docker network as:

```text
http://ollama:11434/v1
```

Do not publish `11434` on `0.0.0.0`. If host access is required for maintenance, bind only to `127.0.0.1:11434` and remove it after use.

External check:

```bash
curl -fsS http://SERVER_IP:11434/api/tags
```

This must fail from the public internet.

## Telegram token rotation

If a token was printed in logs:

1. Revoke and reissue the token in BotFather.
2. Update `/opt/grey-cardinal/.env.production`.
3. Restart `telegram-bot`.
4. Verify logs do not contain `https://api.telegram.org/bot<TOKEN>/...`.

The bot must not log Bot API URLs with the token.

## SSH

Before production deploy:

1. Change the root password.
2. Create or verify a deploy user.
3. Add the deploy user's SSH public key.
4. Set `PasswordAuthentication no`.
5. Set `PermitRootLogin prohibit-password` or `PermitRootLogin no`.
6. Restart SSH and verify key-only login before closing the active session.
7. Ensure the deploy user can run Docker Compose in `/opt/grey-cardinal`.

## Required production secrets

Production readiness fails when these are missing or dev defaults:

- `JWT_SECRET`
- `INTERNAL_API_TOKEN`
- `BOARD_CREDS_ENCRYPTION_KEY`
- `TELEGRAM_BOT_TOKEN`
- working LLM provider settings

Do not commit `.env.production` or service secrets.
