from unittest.mock import AsyncMock

from grey_cardinal_contracts import ActionsResponse
from telegram_bot import webhook
from telegram_bot.handlers import (
    build_callback_event,
    build_command_event,
    build_message_event,
)


def _message(text: str = "Петя, подготовь оплату"):
    return {
        "message_id": 101,
        "date": 1717333200,
        "chat": {"id": -100, "type": "supergroup", "title": "Команда"},
        "from": {"id": 111, "username": "petya", "first_name": "Петя"},
        "text": text,
    }


def test_build_message_event():
    event = build_message_event({"update_id": 1}, _message())
    assert event.message_id == 101
    assert event.chat.id == -100
    assert event.sender.username == "petya"


def test_build_command_event():
    event = build_command_event({"update_id": 2}, _message("/done GC-1"))
    assert event.command == "done"
    assert event.args == ["GC-1"]


def test_build_callback_event():
    callback = {
        "id": "cb-1",
        "from": {"id": 111},
        "message": {"message_id": 102, "chat": {"id": -100}},
        "data": "confirm_task:00000000-0000-0000-0000-000000000001",
    }
    event = build_callback_event({"update_id": 3}, callback)
    assert event.callback_query_id == "cb-1"
    assert event.message.chat_id == -100


def _voice_update():
    return {
        "update_id": 10,
        "message": {
            "message_id": 201,
            "date": 1717333200,
            "chat": {"id": -100, "type": "supergroup", "title": "Team"},
            "from": {"id": 111, "username": "petya", "first_name": "Petya"},
            "voice": {"file_id": "voice-file-id", "duration": 4},
        },
    }


async def test_voice_transcript_is_sent_to_brain_as_clean_message(monkeypatch):
    transcript = "Кардинал, надо сделать задачу для Максима написать API"
    client = AsyncMock()
    client.get_file.return_value = {"file_path": "voice/file.ogg"}
    client.download_file.return_value = b"ogg-bytes"
    brain = AsyncMock()
    brain.send_message_event.return_value = ActionsResponse(actions=[])

    async def fake_transcribe(audio_bytes, file_path):
        assert audio_bytes == b"ogg-bytes"
        assert file_path == "voice/file.ogg"
        return transcript

    monkeypatch.setattr(webhook, "_transcribe", fake_transcribe)

    await webhook.process_update(_voice_update(), client, brain)

    brain.send_message_event.assert_awaited_once()
    event = brain.send_message_event.await_args.args[0]
    assert event.text == transcript
    assert not event.text.startswith("Voice transcript:")
    assert event.raw["gc"]["origin"] == "telegram_voice"
    assert event.raw["message"]["text"] == transcript


async def test_empty_voice_transcript_does_not_call_brain(monkeypatch):
    client = AsyncMock()
    client.get_file.return_value = {"file_path": "voice/file.ogg"}
    client.download_file.return_value = b"ogg-bytes"
    brain = AsyncMock()

    async def fake_transcribe(audio_bytes, file_path):
        return "   "

    monkeypatch.setattr(webhook, "_transcribe", fake_transcribe)

    await webhook.process_update(_voice_update(), client, brain)

    brain.send_message_event.assert_not_called()


async def test_voice_download_failure_does_not_crash_or_call_brain():
    client = AsyncMock()
    client.get_file.return_value = {"file_path": "voice/file.ogg"}
    client.download_file.side_effect = RuntimeError("download failed")
    brain = AsyncMock()

    await webhook.process_update(_voice_update(), client, brain)

    brain.send_message_event.assert_not_called()


async def test_voice_asr_failure_does_not_crash_or_call_brain(monkeypatch):
    client = AsyncMock()
    client.get_file.return_value = {"file_path": "voice/file.ogg"}
    client.download_file.return_value = b"ogg-bytes"
    brain = AsyncMock()

    async def failing_transcribe(audio_bytes, file_path):
        raise RuntimeError("asr failed")

    monkeypatch.setattr(webhook, "_transcribe", failing_transcribe)

    await webhook.process_update(_voice_update(), client, brain)

    brain.send_message_event.assert_not_called()
