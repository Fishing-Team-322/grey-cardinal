"""Конфигурация brain-api (pydantic-settings, читается из окружения)."""

from __future__ import annotations

from pydantic import field_validator
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
    frontend_allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    )
    telegram_bot_base_url: str = "http://telegram-bot:8010"

    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    board_provider: str = "mock"
    yougile_enabled: bool = False
    yougile_api_base_url: str = "https://ru.yougile.com"
    yougile_api_key: str = ""
    yougile_company_id: str = ""
    yougile_project_id: str = ""
    yougile_board_id: str = ""
    yougile_column_backlog_id: str = ""
    yougile_column_todo_id: str = ""
    yougile_column_in_progress_id: str = ""
    yougile_column_review_id: str = ""
    yougile_column_blocked_id: str = ""
    yougile_column_done_id: str = ""
    # Optional assignee → YouGile user-id mapping, JSON string.
    # Example: {"Иван":"user_id_1","Денис":"user_id_2"}
    yougile_user_map: str = ""

    # Demo brain store location. If empty, defaults to {UPLOADS_DIR}/brain/brain.json.
    brain_store_path: str = ""

    reminder_deadline_hours_before: int = 2
    reminder_stale_hours: int = 24
    evening_digest_hour: int = 20
    default_timezone: str = "Europe/Moscow"
    default_workspace_name: str = "Hackathon Team"
    default_telegram_chat_id: int | None = None

    # Политика извлечения задач: порог уверенности и требование глагола-поручения.
    task_extraction_min_confidence: float = 0.65
    task_extraction_require_action_verb: bool = True

    # Порог похожести для детекции дублей (см. FindSimilarTask).
    duplicate_similarity_threshold: float = 0.72

    # Анти-спам политика напоминаний.
    reminder_min_interval_minutes: int = 120
    reminder_max_daily_per_user: int = 3
    reminder_quiet_hours_start: str = "22:00"
    reminder_quiet_hours_end: str = "09:00"

    # ---------------------------------------------------------------------------
    # Telemost bot worker settings
    # ---------------------------------------------------------------------------
    # "mock"       — demo session manager only (default, no browser needed)
    # "playwright" — real browser automation (requires playwright extra)
    telemost_worker_mode: str = "mock"
    telemost_bot_name: str = "Grey Cardinal Bot"
    telemost_join_timeout_sec: int = 60
    telemost_max_meeting_minutes: int = 120

    # ---------------------------------------------------------------------------
    # Dev-only: /demo_core автоматически подтверждает proposal, чтобы показать карточку.
    demo_core_auto_confirm: bool = True

    # Demo/dev mode: automatically confirm proposals from desktop transcripts.
    # When True, the desktop transcript pipeline confirms proposals immediately,
    # making tasks visible in GET /desktop/tasks without manual confirmation.
    # WARNING: do not enable in production.
    desktop_auto_confirm_proposals: bool = False

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.frontend_allowed_origins.split(",") if item.strip()]

    @field_validator("default_telegram_chat_id", mode="before")
    @classmethod
    def blank_chat_id_is_none(cls, value: object) -> object:
        return None if value == "" else value


def get_settings() -> Settings:
    return Settings()
