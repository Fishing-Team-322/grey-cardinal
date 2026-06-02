"""Grey Cardinal telegram-bot — тонкий транспорт между Telegram и brain-api.

Ответственность строго ограничена: приём webhook, нормализация событий, вызов
brain-api, исполнение возвращённых действий через Telegram Bot API. Никакой
бизнес-логики, БД или похода в YouGile здесь нет.
"""

__version__ = "0.1.0"
