"""Быстрый pre-filter очевидного Telegram-шума перед вызовом LLM.

Цель — не гонять в LLM реплики вроде «ок», «спасибо», «+», «👍», которые
заведомо не несут задачи/встречи/отчёта. Фильтр намеренно консервативен:
если в сообщении есть хоть какой-то содержательный сигнал (глагол действия,
время, упоминание, ссылка, длинный текст) — он НЕ считает это шумом и пропускает
сообщение в LLM.

Пример: «да, сделаю сегодня» — НЕ noise (это потенциальный status_update / task),
поэтому уходит в LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from brain_api.application.text_policy import has_action_verb


@dataclass(frozen=True)
class NoisePreFilterResult:
    is_noise: bool
    reason: str | None = None


# Точные короткие подтверждения/реакции. Сравниваем по нормализованному тексту.
_NOISE_PHRASES: frozenset[str] = frozenset(
    {
        "ок",
        "окей",
        "ok",
        "okay",
        "принял",
        "принято",
        "понял",
        "поняла",
        "понятно",
        "ясно",
        "спасибо",
        "спс",
        "спасиб",
        "благодарю",
        "пожалуйста",
        "+",
        "++",
        "да",
        "ага",
        "угу",
        "нет",
        "не",
        "хорошо",
        "отлично",
        "супер",
        "класс",
        "ничего",
        "крутo",
        "круто",
        "согласен",
        "согласна",
        "плюс",
        "готово",  # одно слово без контекста — обычно реакция; при отчёте будут детали
        "лол",
        "хаха",
        "ахах",
        "хех",
    }
)

# Эмодзи-реакции: если после удаления эмодзи/пунктуации ничего не остаётся — шум.
_EMOJI_OR_PUNCT_RE = re.compile(
    r"[\s\.,!?;:)\(\-—–\"'«»…]+"
    r"|[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF❤️‍]+"
)
_WORD_RE = re.compile(r"[a-zA-Zа-яёА-ЯЁ0-9]+")
# Время / @упоминание / ссылка — сильные признаки содержательности.
_SIGNAL_RE = re.compile(r"\d{1,2}[:.]\d{2}|@\w+|https?://|\bt\.me/")


class NoisePreFilter:
    """Дешёвый детектор очевидного шума (без LLM)."""

    def check(self, text: str | None) -> NoisePreFilterResult:
        raw = (text or "").strip()
        if not raw:
            return NoisePreFilterResult(is_noise=True, reason="empty")

        lowered = raw.lower()

        # 1. Сообщение из одних эмодзи/пунктуации — реакция, не задача.
        without_emoji = _EMOJI_OR_PUNCT_RE.sub("", raw)
        if not without_emoji:
            return NoisePreFilterResult(is_noise=True, reason="emoji_only")

        # 2. Есть содержательный сигнал (время/упоминание/ссылка) — пропускаем.
        if _SIGNAL_RE.search(lowered):
            return NoisePreFilterResult(is_noise=False)

        words = _WORD_RE.findall(lowered)
        word_count = len(words)

        # 3. Точное совпадение короткой реплики со списком шума.
        normalized = "".join(ch for ch in lowered if ch not in "!?.,…)( ")
        if normalized in _NOISE_PHRASES:
            return NoisePreFilterResult(is_noise=True, reason="ack_phrase")

        # 4. Одно-два слова, оба из списка шума («ок спасибо», «да понял»).
        if 0 < word_count <= 2 and all(w in _NOISE_PHRASES for w in words):
            return NoisePreFilterResult(is_noise=True, reason="ack_phrase")

        # 5. Короткое сообщение без глагола действия и без сигналов — вероятно шум,
        #    но осторожно: «да, сделаю сегодня» содержит глагол -> не шум.
        if word_count <= 2 and not has_action_verb(raw):
            # Двусловные реплики без действия («ну ладно», «как дела») — шум.
            return NoisePreFilterResult(is_noise=True, reason="too_short")

        return NoisePreFilterResult(is_noise=False)
