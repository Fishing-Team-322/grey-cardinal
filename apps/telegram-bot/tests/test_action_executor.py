from unittest.mock import AsyncMock

from grey_cardinal_contracts import (
    AnswerCallbackAction,
    EditMessageAction,
    SendMessageAction,
)
from telegram_bot.renderer import execute_actions


async def test_execute_actions_calls_telegram_client_methods():
    client = AsyncMock()
    await execute_actions(
        client,
        [
            SendMessageAction(chat_id=1, text="send"),
            EditMessageAction(chat_id=1, message_id=2, text="edit"),
            AnswerCallbackAction(callback_query_id="cb-1", text="answer"),
        ],
    )
    client.send_message.assert_awaited_once_with(1, "send", None)
    client.edit_message_text.assert_awaited_once_with(1, 2, "edit", None)
    client.answer_callback_query.assert_awaited_once_with("cb-1", "answer", False)
