from telegram_bot.commands import is_command, parse_command


def test_parse_status_command():
    assert parse_command("/done GC-1") == ("done", ["GC-1"])


def test_parse_tasks_and_digest_commands():
    assert parse_command("/tasks") == ("tasks", [])
    assert parse_command("/digest@GreyCardinalBot") == ("digest", [])


def test_is_command():
    assert is_command(" /tasks") is True
    assert is_command("обычный текст") is False
