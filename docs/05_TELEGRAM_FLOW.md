# Telegram flow

`TELEGRAM_MODE` can be:

- `polling`
- `webhook`

Current production default is polling. In polling mode the bot deletes webhook state on startup and calls `getUpdates`, using `HTTPS_PROXY` when configured.

Webhook route:

```text
/webhooks/telegram -> telegram-bot:8010
```

Telegram tokens must not be logged. Never log full Bot API URLs.

Unlinked team chat behavior:

```text
Этот чат ещё не привязан к команде Grey Cardinal.
Менеджер команды должен привязать его в настройках команды.
```
