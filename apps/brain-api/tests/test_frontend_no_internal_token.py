"""Item 3 (frontend): браузерный клиент не должен использовать internal-доступ.

Фронт ходит только в публичные /api/* через cookie-сессию. Запрещены:
X-Internal-Token, *internalToken, GC_INTERNAL_TOKEN и любые прямые /internal/* вызовы.
"""

from pathlib import Path

import pytest

FRONTEND_JS = Path(__file__).resolve().parents[3] / "apps" / "frontend" / "public" / "js"
FORBIDDEN = ["X-Internal-Token", "internalToken", "GC_INTERNAL_TOKEN", "/internal/"]


@pytest.mark.parametrize("needle", FORBIDDEN)
def test_frontend_has_no_internal_access(needle):
    offenders = []
    for path in FRONTEND_JS.glob("*.jsx"):
        if needle in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    assert not offenders, f"{needle!r} найден во фронте: {offenders}"
