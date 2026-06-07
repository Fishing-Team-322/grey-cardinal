import re
from pathlib import Path

FRONTEND_CADDYFILE = Path(__file__).resolve().parents[2] / "frontend" / "Caddyfile"


def test_frontend_downloads_do_not_fall_back_to_spa_index() -> None:
    text = FRONTEND_CADDYFILE.read_text(encoding="utf-8")

    assert "handle /downloads/*" in text
    match = re.search(r"handle /downloads/\* \{(?P<body>.*?)^\s*\}", text, re.MULTILINE | re.DOTALL)
    assert match is not None
    downloads_block = match.group("body")
    assert "try_files" not in downloads_block
