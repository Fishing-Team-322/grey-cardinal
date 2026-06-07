from brain_api.application.rendering import format_telegram_mention


def test_bot_prefers_username_for_mention():
    assert format_telegram_mention("Денис", "@denis", 123) == "@denis"


def test_bot_uses_text_mention_without_username():
    assert (
        format_telegram_mention("<Денис>", None, 123)
        == '<a href="tg://user?id=123">&lt;Денис&gt;</a>'
    )


def test_bot_falls_back_to_plain_name_without_telegram_binding():
    assert format_telegram_mention("Денис") == "Денис"
