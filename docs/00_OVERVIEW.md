# Обзор

P0 Grey Cardinal принимает сообщения Telegram и transcript-события, извлекает возможные задачи,
просит подтверждение и после callback создаёт локальную задачу с карточкой на доске.

Главное правило: `brain-api` - единственный владелец PostgreSQL и task lifecycle.
`telegram-bot`, `audio-worker`, native audio-agent и dashboard являются клиентами.

## Готовый поток

```text
Telegram message
  -> telegram-bot
  -> brain-api
  -> task proposal
  -> confirm_task:<uuid>
  -> PostgreSQL task GC-1
  -> MockBoardGateway / YouGileBoardGateway
  -> /tasks, /start_task, /block, /done, /digest
```

Transcript flow:

```text
audio-worker
  -> POST /internal/audio/transcript
  -> brain-api
  -> transcript_events
  -> proposal
  -> Telegram action в default chat, если он уже известен
```
