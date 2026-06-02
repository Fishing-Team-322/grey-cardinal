"""Grey Cardinal audio-worker (P0 — только каркас).

На P0 реальный аудио-pipeline (system audio capture / ASR / VAD) НЕ реализован.
Есть healthcheck, контракты и mock-отправка transcript-события в brain-api как
задел под P1.
"""

__version__ = "0.1.0"
