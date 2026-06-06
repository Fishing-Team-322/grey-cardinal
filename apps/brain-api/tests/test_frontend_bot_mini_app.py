from pathlib import Path

FRONTEND_JS = Path(__file__).resolve().parents[2] / "frontend" / "public" / "js"


def test_telegram_menu_root_opens_bot_settings_mini_app() -> None:
    router = (FRONTEND_JS / "main.jsx").read_text(encoding="utf-8")
    mini_app = (FRONTEND_JS / "bot-settings.jsx").read_text(encoding="utf-8")

    assert "if (h === '/' && tg && tg.initData) return '/tg';" in router
    assert "['leaderboard','Лидерборд']" in mini_app
    assert "['reports','Отчёты']" in mini_app
    assert "['profile','Профиль']" in mini_app
