"""Конфигурация telegram-bot."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "dev"
    log_level: str = "INFO"
    internal_api_token: str = "dev-internal-token"

    telegram_bot_host: str = "0.0.0.0"
    telegram_bot_port: int = 8010
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_public_base_url: str = ""

    # Long-polling mode: the bot pulls updates from Telegram (outbound) instead
    # of receiving webhooks. Use when Telegram cannot reach the webhook (e.g. the
    # host's network blocks inbound Telegram delivery).
    telegram_use_polling: bool = False
    telegram_mode: str = "webhook"
    telegram_poll_timeout: int = 25

    brain_api_base_url: str = "http://brain-api:8000"

    @property
    def telegram_api_base(self) -> str:
        return f"https://api.telegram.org/bot{self.telegram_bot_token}"

    @property
    def use_polling(self) -> bool:
        return self.telegram_mode == "polling" or self.telegram_use_polling

    @field_validator("telegram_mode")
    @classmethod
    def validate_telegram_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"polling", "webhook"}:
            raise ValueError("TELEGRAM_MODE must be polling or webhook")
        return value


def get_settings() -> Settings:
    return Settings()
