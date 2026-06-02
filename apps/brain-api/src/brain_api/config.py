"""Конфигурация brain-api (pydantic-settings, читается из окружения)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "dev"
    log_level: str = "INFO"
    internal_api_token: str = "dev-internal-token"

    database_url: str = "postgresql+asyncpg://grey:grey@postgres:5432/grey_cardinal"
    db_echo: bool = False

    brain_api_host: str = "0.0.0.0"
    brain_api_port: int = 8000

    telegram_bot_base_url: str = "http://telegram-bot:8010"

    # LLM
    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # Board
    board_provider: str = "mock"
    yougile_api_base_url: str = "https://ru.yougile.com"
    yougile_api_key: str = ""
    yougile_company_id: str = ""
    yougile_project_id: str = ""
    yougile_board_id: str = ""
    yougile_column_todo_id: str = ""
    yougile_column_in_progress_id: str = ""
    yougile_column_blocked_id: str = ""
    yougile_column_done_id: str = ""

    # Reminders
    reminder_deadline_hours_before: int = 2
    reminder_stale_hours: int = 24
    evening_digest_hour: int = 20
    default_timezone: str = "Europe/Moscow"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)


def get_settings() -> Settings:
    return Settings()
