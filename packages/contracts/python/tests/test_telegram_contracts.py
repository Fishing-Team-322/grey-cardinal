from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from grey_cardinal_contracts import (
    ActionsResponse,
    SendMessageAction,
    TelegramCallbackEvent,
    TelegramChatInfo,
    TelegramMessageEvent,
    TelegramMessageRef,
    TelegramSender,
)


def test_message_event_validates_nested_contracts():
    event = TelegramMessageEvent(
        update_id=1,
        message_id=101,
        chat=TelegramChatInfo(id=-100, type="supergroup", title="Команда"),
        sender=TelegramSender(id=111, username="petya", first_name="Петя"),
        text="Петя, подготовь оплату",
        date=datetime.now(UTC),
    )
    assert event.chat.id == -100
    assert event.raw == {}


def test_callback_event_accepts_stable_callback_format():
    confirmation_id = uuid4()
    event = TelegramCallbackEvent(
        update_id=2,
        callback_query_id="cb-1",
        from_user=TelegramSender(id=111),
        message=TelegramMessageRef(message_id=102, chat_id=-100),
        data=f"confirm_task:{confirmation_id}",
    )
    assert event.data == f"confirm_task:{confirmation_id}"


def test_actions_response_rejects_unknown_action_type():
    with pytest.raises(ValidationError):
        ActionsResponse.model_validate({"actions": [{"type": "delete_message", "chat_id": 1}]})


def test_send_message_action_has_stable_discriminator():
    response = ActionsResponse(actions=[SendMessageAction(chat_id=1, text="ok")])
    assert response.model_dump()["actions"][0]["type"] == "send_message"
