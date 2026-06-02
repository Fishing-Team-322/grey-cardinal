from uuid import uuid4

from telegram_bot.callbacks import split_callback


def test_split_confirm_and_reject_callbacks():
    target = str(uuid4())
    assert split_callback(f"confirm_task:{target}") == ("confirm_task", target)
    assert split_callback(f"reject_task:{target}") == ("reject_task", target)


def test_split_callback_without_payload():
    assert split_callback("confirm_task") == ("confirm_task", None)
