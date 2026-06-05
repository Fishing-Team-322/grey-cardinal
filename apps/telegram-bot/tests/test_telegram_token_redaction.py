from telegram_bot.logging import redact_telegram_token


def test_redact_telegram_token_from_api_urls() -> None:
    value = (
        "https://api.telegram.org/bot123456:SECRET/sendMessage "
        "https://api.telegram.org/file/bot123456:SECRET/voice/file.ogg"
    )

    redacted = redact_telegram_token(value)

    assert "123456:SECRET" not in redacted
    assert "https://api.telegram.org/bot<redacted>/sendMessage" in redacted
    assert "https://api.telegram.org/file/bot<redacted>/voice/file.ogg" in redacted
