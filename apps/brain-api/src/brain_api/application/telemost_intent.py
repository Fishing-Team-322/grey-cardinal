"""Deterministic "let's have a call" intent detection for Telegram messages.

Intentionally rule-based (not LLM): the MVP must reliably catch explicit call
phrases and just *ask* — it never creates a room automatically. Keep this cheap,
testable, and conservative (favour false negatives over false positives, so the
bot doesn't nag on unrelated chatter).
"""

from __future__ import annotations

import re

# Each pattern matches a clear request for a voice/video call.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"созвон"),  # созвон, созвонимся, «го созвон», «созвон по задаче»
    re.compile(r"созвонит"),                     # созвониться / созвонимся
    re.compile(r"созвонимся"),
    re.compile(r"телемост"),
    re.compile(r"\btelemost\b"),
    re.compile(r"видеозвон|видео-?звон|видео-?встреч"),
    re.compile(r"(?:обсуд\w*|поговор\w*|пообща\w*)\s+(?:по\s+)?голос"),  # «обсудить голосом»
    re.compile(r"голос\w*\s+(?:обсуд\w*|поговор\w*)"),
)


def detect_call_intent(text: str | None) -> bool:
    """True if the message is asking to get on a call."""
    if not text:
        return False
    normalized = text.lower().replace("ё", "е")
    return any(pattern.search(normalized) for pattern in _PATTERNS)
