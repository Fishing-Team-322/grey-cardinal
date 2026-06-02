"""Конфигурация audio-worker."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "dev"
    log_level: str = "INFO"
    internal_api_token: str = "dev-internal-token"

    audio_worker_host: str = "0.0.0.0"
    audio_worker_port: int = 8020

    brain_api_base_url: str = "http://brain-api:8000"


def get_settings() -> Settings:
    return Settings()
