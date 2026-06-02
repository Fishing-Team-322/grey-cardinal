"""Конфигурация telegram-bot."""

from __future__ import annotations

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

    brain_api_base_url: str = "http://brain-api:8000"

    @property
    def telegram_api_base(self) -> str:
        return f"https://api.telegram.org/bot{self.telegram_bot_token}"


def get_settings() -> Settings:
    return Settings()
