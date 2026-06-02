"""Grey Cardinal brain-api — центральный сервис («мозг»).

Владеет task lifecycle, LLM-экстракцией, confirmations, reminders, board-адаптерами,
websocket-событиями и единолично пишет в PostgreSQL.
"""

__version__ = "0.1.0"
