"""Контракты audio-worker.

Основной контракт — TranscriptEvent из общего пакета. Здесь он переэкспортируется
и описаны будущие (P1) контракты пайплайна.

Будущие контракты P1 (НЕ реализованы на P0):
  - AudioChunk:   сырые аудио-фреймы с устройства/virtual cable.
  - VadSegment:   границы речи после VAD.
  - AsrPartial:   промежуточная гипотеза ASR (is_final=false).
  - AsrFinal:     финальная реплика (is_final=true) -> TranscriptEvent -> brain-api.
  - SpeakerTurn:  результат диаризации (speaker_id/speaker_name).
"""

from __future__ import annotations

from grey_cardinal_contracts import TranscriptEvent

__all__ = ["TranscriptEvent"]
