"""Pure mood/pet computation — без I/O, легко тестируется.

Связывает эмоциональные сигналы отдела и здоровье задач в единое настроение
команды и состояние питомца. См. docs/design/gamification-tamagotchi.md.
"""

from __future__ import annotations

from dataclasses import dataclass


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class MoodInputs:
    """Нормализованные входы для расчёта настроения.

    emotion_valence/emotion_stress — None, если эмоциональный анализ выключен
    или сигналов нет (тогда настроение считается только по задачам).
    """

    emotion_valence: float | None = None  # -1..1 (негатив..позитив)
    emotion_stress: float | None = None   # 0..1
    task_health: float = 0.6              # 0..1 — доля задач без просрочки
    overdue_pressure: float = 0.0         # 0..1 — давление просрочек
    activity: float = 0.0                 # 0..1 — недавняя активность (закрытия/синки)


# Веса вклада компонентов в настроение.
_W_EMOTION = 0.34
_W_TASK = 0.30
_W_OVERDUE = 0.24
_W_ACTIVITY = 0.12


def compute_mood(inp: MoodInputs) -> float:
    """Свести входы в настроение 0..1 (0 — грустный, 1 — счастливый)."""
    mood = 0.5
    if inp.emotion_valence is not None:
        emotion = inp.emotion_valence  # -1..1
        if inp.emotion_stress is not None:
            emotion -= inp.emotion_stress  # стресс тянет вниз
        mood += _W_EMOTION * _clamp(emotion, -1.0, 1.0)
    mood += _W_TASK * ((_clamp(inp.task_health) - 0.5) * 2)
    mood -= _W_OVERDUE * _clamp(inp.overdue_pressure)
    mood += _W_ACTIVITY * _clamp(inp.activity)
    return round(_clamp(mood), 3)


# Состояния питомца: порядок проверки важен (tired/sad перебивают).
PET_STATES = ("happy", "content", "neutral", "tired", "sad")

_STATE_EMOJI = {
    "happy": "😄",
    "content": "🙂",
    "neutral": "😐",
    "tired": "😪",
    "sad": "😢",
}

_STATE_PHRASE = {
    "happy": "Команда в потоке — питомец сияет!",
    "content": "Всё ровно, питомец доволен.",
    "neutral": "Питомец спокоен, но приглядывает за командой.",
    "tired": "Питомец подустал — команде не хватает энергии.",
    "sad": "Питомец загрустил вместе с командой 💛",
}


def pet_state(mood: float, energy: float) -> str:
    """Определить визуальное состояние питомца из настроения и энергии."""
    if energy < 0.28:
        return "tired"
    if mood < 0.38:
        return "sad"
    if mood >= 0.75 and energy >= 0.45:
        return "happy"
    if mood >= 0.55:
        return "content"
    return "neutral"


def state_emoji(state: str) -> str:
    return _STATE_EMOJI.get(state, "😐")


def state_phrase(state: str) -> str:
    return _STATE_PHRASE.get(state, "")


def decay_energy(energy: float, hours_elapsed: float, *, per_day: float = 0.25) -> float:
    """Энергия питомца падает со временем (нужно «кормить» закрытием задач)."""
    if hours_elapsed <= 0:
        return _clamp(energy)
    return round(_clamp(energy - per_day * (hours_elapsed / 24.0)), 3)


def level_for_pet_xp(xp: int, *, per_level: int = 100) -> int:
    return max(1, xp // per_level + 1)


# ── Лёгкий лексический сентимент (fallback, если LLM не дал affect) ────────────

_POSITIVE_LEX = (
    "спасибо", "класс", "круто", "супер", "отлично", "огонь", "рад", "ура",
    "молодец", "красава", "получилось", "победа", "топ", "🔥", "👍", "🎉", "😄", "❤",
)
_NEGATIVE_LEX = (
    "устал", "выгор", "бес", "раздраж", "злюсь", "плохо", "ужас", "капец",
    "не успева", "завал", "проблем", "стресс", "тяжело", "грустно", "😡", "😞", "😢", "💀",
)
_STRESS_LEX = (
    "срочно", "горит", "дедлайн", "аврал", "не успева", "завал", "капец", "паника",
    "помогите", "сломал", "критич",
)


def heuristic_affect(text: str) -> tuple[float, float] | None:
    """Грубая оценка (valence, stress) по лексике. None — если сигналов нет."""
    if not text:
        return None
    low = text.lower().replace("ё", "е")
    pos = sum(1 for w in _POSITIVE_LEX if w in low)
    neg = sum(1 for w in _NEGATIVE_LEX if w in low)
    stress_hits = sum(1 for w in _STRESS_LEX if w in low)
    if pos == 0 and neg == 0 and stress_hits == 0:
        return None
    valence = _clamp((pos - neg) / 3.0, -1.0, 1.0)
    stress = _clamp(stress_hits / 3.0 + (neg / 4.0), 0.0, 1.0)
    return round(valence, 3), round(stress, 3)
