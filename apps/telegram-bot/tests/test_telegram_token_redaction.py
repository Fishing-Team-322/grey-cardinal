import logging

from telegram_bot.logging import TelegramTokenRedactionFilter, redact_telegram_token


def test_redact_telegram_token_from_api_urls() -> None:
    value = (
        "https://api.telegram.org/bot123456:SECRET/sendMessage "
        "https://api.telegram.org/file/bot123456:SECRET/voice/file.ogg"
    )

    redacted = redact_telegram_token(value)

    assert "123456:SECRET" not in redacted
    assert "https://api.telegram.org/bot<redacted>/sendMessage" in redacted
    assert "https://api.telegram.org/file/bot<redacted>/voice/file.ogg" in redacted


def test_redaction_filter_scrubs_formatted_log_arguments() -> None:
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: %s "%s"',
        args=("POST", "https://api.telegram.org/bot123456:SECRET/getUpdates"),
        exc_info=None,
    )

    assert TelegramTokenRedactionFilter().filter(record)
    rendered = record.getMessage()

    assert "123456:SECRET" not in rendered
    assert "bot<redacted>/getUpdates" in rendered
