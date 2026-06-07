# Telegram Topics

Telegram topics становятся Source Stream для задач.

Schema:
- `chat_messages.message_thread_id`
- `telegram_topic_bindings`

Backend:
- `GET /api/teams/{teamId}/telegram/topics`
- `POST /api/teams/{teamId}/telegram/topics`

Frontend:
- `/app/teams/:teamId/telegram/topics`

Если Telegram update содержит `message_thread_id`, bot-normalizer передает его в `TelegramMessageEvent`, backend сохраняет его в `chat_messages`, после чего topic можно привязать к team/board/source name.

Если Telegram Bot API update не содержит `message_thread_id`, старый flow не ломается: поле nullable, topic mapping просто будет пустым до появления topic-сообщений.
