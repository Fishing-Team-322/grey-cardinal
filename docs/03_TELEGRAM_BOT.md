# Telegram bot

## Создание и подключение

1. Создайте бота через `@BotFather` командой `/newbot`.
2. Для группы отключите privacy mode: `/setprivacy` → выбрать бота → `Disable`.
3. Добавьте бота в нужный чат.
4. Заполните локальные переменные окружения:

```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_PUBLIC_BASE_URL=https://your-public-host
export TELEGRAM_WEBHOOK_SECRET=...
```

Секреты не коммитятся в git.

## Webhook и команды

```bash
make set-telegram-webhook
make get-telegram-webhook-info
make set-telegram-commands
```

Webhook ставится на `{TELEGRAM_PUBLIC_BASE_URL}/webhooks/telegram`. Если
`TELEGRAM_WEBHOOK_SECRET` пуст, параметр `secret_token` не отправляется.

## Настройка чата

После добавления бота в группу:

```text
/start
/bind_chat
/meeting_start
```

`/bind_chat` привязывает группу к workspace и делает ее notification chat для
transcript proposals.
