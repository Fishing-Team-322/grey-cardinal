"""Item 3: production Caddyfile должен закрывать публичный доступ к /internal/*."""

from pathlib import Path

CADDYFILE = Path(__file__).resolve().parents[3] / "Caddyfile"


def test_caddyfile_denies_internal_paths():
    text = CADDYFILE.read_text(encoding="utf-8")
    # Должен быть явный handle /internal/* { respond 404 } (а не проксирование).
    assert "handle /internal/*" in text, "нет блока handle /internal/*"
    # Оба server-блока (fishingteam.su и api.fishingteam.su) должны его содержать.
    assert text.count("handle /internal/*") >= 2, (
        "оба домена (fishingteam.su и api.fishingteam.su) должны закрывать /internal/*"
    )
    # Старая дыра: голый reverse_proxy для api.* без фильтра /internal/* недопустима.
    assert "/internal/debug/health/dependencies" not in text, (
        "internal debug endpoint больше не должен публиковаться наружу"
    )
