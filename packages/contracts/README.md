# packages/contracts

Единый источник истины для **межсервисных контрактов** Grey Cardinal. Чтобы
`telegram-bot`, `brain-api`, `audio-worker` и `frontend-dashboard` «говорили на
одном языке», все DTO определяются здесь и нигде не дублируются руками.

## Структура

```text
packages/contracts/
  python/
    grey_cardinal_contracts/   # Pydantic v2 модели (устанавливаемый пакет)
      telegram.py              # нормализованные Telegram-события + действия бота
      tasks.py                 # статусы/приоритеты задач, TaskDTO, результат экстракции
      board.py                 # провайдеры доски, BoardCardResult
      transcripts.py           # TranscriptEvent (audio-worker -> brain-api)
      events.py                # websocket-события для dashboard
  typescript/
    src/                       # TS-зеркало для frontend-dashboard
      telegram.ts
      tasks.ts
      transcripts.ts
      events.ts
```

## Использование (Python)

Пакет устанавливается как зависимость в каждый Python-сервис:

```bash
pip install -e packages/contracts/python
```

```python
from grey_cardinal_contracts import (
    TelegramMessageEvent,
    ActionsResponse,
    SendMessageAction,
    TaskExtractionResult,
    WebsocketEvent,
)
```

## Использование (TypeScript)

`frontend-dashboard` импортирует типы напрямую из исходников (через alias в Vite):

```ts
import type { WebsocketEvent, TaskDTO } from "@contracts/events";
```

## Правило

Любое изменение контракта правится **сначала здесь**, затем синхронизируется в
обеих реализациях (Python + TypeScript). Контракты также продублированы в
`docs/` (`04_BRAIN_API.md`, `03_TELEGRAM_BOT.md`).
