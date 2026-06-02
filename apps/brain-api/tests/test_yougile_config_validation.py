from brain_api.infrastructure.board.base import YouGileConfig


def test_yougile_config_lists_missing_required_env():
    config = YouGileConfig(api_base_url="https://ru.yougile.com", api_key="")

    assert config.is_configured is False
    assert config.missing_required == [
        "YOUGILE_API_KEY",
        "YOUGILE_COMPANY_ID",
        "YOUGILE_PROJECT_ID",
        "YOUGILE_BOARD_ID",
        "YOUGILE_COLUMN_TODO_ID",
    ]


def test_yougile_config_accepts_minimum_required_env():
    config = YouGileConfig(
        api_base_url="https://ru.yougile.com",
        api_key="token",
        company_id="company",
        project_id="project",
        board_id="board",
        column_todo_id="todo",
    )

    assert config.is_configured is True
