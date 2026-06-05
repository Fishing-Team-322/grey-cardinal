"""Runtime settings for brain-api."""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "dev"
    log_level: str = "INFO"
    internal_api_token: str = "dev-internal-token"

    jwt_secret: str = "change-me-in-production-use-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 30
    jwt_cookie_name: str = "gc_session"
    jwt_cookie_secure: bool = True

    database_url: str = "postgresql+asyncpg://grey:grey@postgres:5432/grey_cardinal"
    db_echo: bool = False

    brain_api_host: str = "0.0.0.0"
    brain_api_port: int = 8000
    frontend_allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    )
    telegram_bot_base_url: str = "http://telegram-bot:8010"
    telegram_bot_username: str = "grey_cyrdinyl_bot"
    telegram_bot_token: str = ""
    telegram_mode: str = "polling"
    telegram_webhook_secret: str = ""
    telegram_public_base_url: str = ""

    llm_provider: str = "local"
    llm_local_base_url: str = "http://ollama:11434/v1"
    llm_external_base_url: str = ""
    llm_external_api_key: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "qwen2.5:7b"
    llm_timeout_seconds: int = 20
    llm_max_retries: int = 2
    llm_strict_json: bool = True

    board_provider: str = "yougile"
    board_creds_encryption_key: str = ""

    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = ""
    jira_done_transition_id: str = "31"
    jira_in_progress_transition_id: str = "21"

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
    yougile_user_map: str = ""

    brain_store_path: str = ""
    uploads_dir: str = "/data/uploads"

    reminder_deadline_hours_before: int = 2
    reminder_stale_hours: int = 24
    morning_summary_hour: int = 9
    evening_digest_hour: int = 20
    default_timezone: str = "Europe/Moscow"
    default_workspace_name: str = "Hackathon Team"
    default_telegram_chat_id: int | None = None

    task_extraction_min_confidence: float = 0.65
    task_extraction_require_action_verb: bool = True
    duplicate_similarity_threshold: float = 0.72

    reminder_min_interval_minutes: int = 120
    reminder_max_daily_per_user: int = 3
    reminder_quiet_hours_start: str = "22:00"
    reminder_quiet_hours_end: str = "09:00"

    demo_core_auto_confirm: bool = True

    # Daemon / meeting state-machine окна.
    meeting_arm_minutes_before: int = 5
    meeting_default_duration_minutes: int = 60

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.frontend_allowed_origins.split(",") if item.strip()]

    @property
    def effective_llm_base_url(self) -> str:
        if self.llm_provider == "local":
            return self.llm_local_base_url or self.llm_base_url
        if self.llm_provider == "external_api":
            return self.llm_external_base_url or self.llm_base_url
        return self.llm_base_url

    @property
    def effective_llm_api_key(self) -> str:
        if self.llm_provider == "external_api":
            return self.llm_external_api_key or self.llm_api_key
        return self.llm_api_key

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "disabled":
            return False
        if self.llm_provider == "local":
            return bool(self.effective_llm_base_url and self.llm_model)
        if self.llm_provider == "external_api":
            return bool(
                self.effective_llm_base_url and self.effective_llm_api_key and self.llm_model
            )
        return False

    @property
    def storage_paths(self) -> list[Path]:
        return [Path(self.uploads_dir)]

    def production_config_errors(self) -> list[str]:
        if not self.is_production:
            return []
        errors: list[str] = []
        if not self.database_url:
            errors.append("DATABASE_URL must be set in production")
        if self.llm_provider == "disabled":
            errors.append("LLM_PROVIDER=disabled is not allowed in production")
        if self.llm_provider in {"local", "external_api"} and not self.effective_llm_base_url:
            errors.append("LLM base URL must be set in production")
        if self.llm_provider in {"local", "external_api"} and not self.llm_model:
            errors.append("LLM_MODEL must be set in production")
        if self.llm_provider == "external_api" and not self.effective_llm_api_key:
            errors.append("LLM_EXTERNAL_API_KEY must be set for external_api in production")
        if self.llm_provider == "disabled" or not self.llm_enabled:
            errors.append("LLM provider must be configured in production")
        if not self.jwt_secret or self.jwt_secret.startswith("change-me"):
            errors.append("JWT_SECRET must be set in production")
        if not self.internal_api_token or self.internal_api_token == "dev-internal-token":
            errors.append("INTERNAL_API_TOKEN must be set in production")
        if not self.board_creds_encryption_key:
            errors.append("BOARD_CREDS_ENCRYPTION_KEY must be set in production")
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN must be set in production")
        if self.board_provider == "mock":
            errors.append("BOARD_PROVIDER=mock is not allowed in production")
        return errors

    @field_validator("default_telegram_chat_id", mode="before")
    @classmethod
    def blank_chat_id_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        value = value.strip().lower()
        allowed = {"local", "external_api", "disabled"}
        if value not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of: {', '.join(sorted(allowed))}")
        return value

    @field_validator("telegram_mode")
    @classmethod
    def validate_telegram_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"polling", "webhook"}:
            raise ValueError("TELEGRAM_MODE must be polling or webhook")
        return value


def get_settings() -> Settings:
    return Settings()
