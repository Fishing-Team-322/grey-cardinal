# Architecture v2

Production stack:

- `brain-api`: FastAPI domain/API service.
- `telegram-bot`: polling or webhook Telegram adapter.
- `audio-worker`: upload endpoint and ASR client.
- `asr-service`: HTTP faster-whisper service.
- `frontend`: static app.
- `postgres`: application database.
- `ollama`: local OpenAI-compatible LLM endpoint inside Docker network.
- `tg-proxy`: Telegram outbound proxy.
- `caddy`: public TLS reverse proxy.

Semantic flow:

```text
Telegram update
  -> telegram-bot
  -> brain-api /internal/telegram/message
  -> Team by tg_chat_id
  -> SemanticMessageParser
  -> task/meeting/report/absence/status/noise route
```

Production readiness checks database, migrations, mandatory secrets, Telegram config, LLM provider, and writable storage.
