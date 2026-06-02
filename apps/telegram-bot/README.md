# telegram-bot

Тонкий Telegram-транспорт Grey Cardinal. **Не содержит бизнес-логики**: только
приём webhook, нормализация событий, вызов brain-api и исполнение возвращённых
действий через Telegram Bot API.

## Что делает

1. Принимает `POST /webhooks/telegram` (с проверкой секрета вебхука).
2. Разбирает update: `message` / `command` / `callback_query`.
3. Нормализует в контрактные события (`packages/contracts`).
4. Отправляет их в brain-api (`/internal/telegram/*`) с `X-Internal-Token`.
5. Получает `ActionsResponse` и исполняет действия: `sendMessage`,
   `editMessageText`, `answerCallbackQuery`.

Дополнительно предоставляет internal-эндпоинты, чтобы brain-api мог инициировать
отправку (reminders/digest):

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/health` | liveness |
| POST | `/webhooks/telegram` | приём Telegram-update |
| POST | `/internal/send-message` | отправка сообщения (для reminders) |
| POST | `/internal/edit-message` | редактирование сообщения |
| POST | `/internal/answer-callback` | ответ на callback |

## Запуск локально

```bash
pip install -e packages/contracts/python
pip install -e "apps/telegram-bot[dev]"
export TELEGRAM_BOT_TOKEN=123:abc
export BRAIN_API_BASE_URL=http://localhost:8000
uvicorn telegram_bot.main:app --reload --port 8010
```

## Регистрация webhook

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d "url=$TELEGRAM_PUBLIC_BASE_URL/webhooks/telegram" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET" \
  -d 'allowed_updates=["message","callback_query"]'
```

> Для чтения групповых сообщений отключите privacy mode у @BotFather:
> `/setprivacy` → выбрать бота → **Disable**.

## Тесты

```bash
pytest apps/telegram-bot/tests -q
```
