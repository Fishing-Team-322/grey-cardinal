from pathlib import Path

FRONTEND_CADDYFILE = Path(__file__).resolve().parents[2] / "frontend" / "Caddyfile"


def test_frontend_downloads_do_not_fall_back_to_spa_index() -> None:
    text = FRONTEND_CADDYFILE.read_text(encoding="utf-8")

    assert "handle /downloads/*" in text
    downloads_block = text.split("handle /downloads/*", 1)[1].split("handle {", 1)[0]
    assert "try_files" not in downloads_block
