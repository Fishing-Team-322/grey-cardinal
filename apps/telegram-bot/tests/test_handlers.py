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
