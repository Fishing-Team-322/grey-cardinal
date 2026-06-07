from pathlib import Path

FRONTEND_JS = Path(__file__).resolve().parents[2] / "frontend" / "public" / "js"


def test_telegram_settings_and_related_views_are_registered() -> None:
    shell = (FRONTEND_JS / "shell.js").read_text(encoding="utf-8")
    telegram = (FRONTEND_JS / "views" / "telegram.js").read_text(encoding="utf-8")

    assert '"/app/integrations/telegram"' in shell
    assert '"/app/leaderboard"' in shell
    assert '"/app/settings"' in shell
    assert "api.telegram" in telegram
