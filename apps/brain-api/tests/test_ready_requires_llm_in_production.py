from brain_api.config import Settings


def test_ready_requires_llm_in_production():
    settings = Settings(
        app_env="production",
        llm_provider="disabled",
        jwt_secret="prod-secret",
        internal_api_token="prod-internal",
        board_creds_encryption_key="prod-board-key",
        telegram_bot_token="123:token",
    )

    assert "LLM provider must be configured in production" in settings.production_config_errors()
