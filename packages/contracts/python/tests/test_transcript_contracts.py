from datetime import UTC, datetime

from grey_cardinal_contracts import TranscriptEvent


def test_transcript_defaults_to_final_and_has_type():
    event = TranscriptEvent(text="Аня, проверь интеграцию", ts=datetime.now(UTC))
    assert event.type == "transcript"
    assert event.is_final is True
    assert event.raw == {}
