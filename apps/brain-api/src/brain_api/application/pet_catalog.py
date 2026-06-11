"""Серверный каталог предметов командного питомца.

Единый источник правды о косметике: id, категория, редкость, условие разблокировки
и (для авто-анлока) машиночитаемое правило ``unlock_rule``. Frontend рендерит
инвентарь из API, который опирается на этот каталог. См. docs CLAUDE_BACKEND_TZ.
"""

from __future__ import annotations

from typing import Any, TypedDict

CATEGORIES: list[dict[str, str]] = [
    {"id": "hat", "label": "Головные уборы"},
    {"id": "glasses", "label": "Очки"},
    {"id": "scarf", "label": "Шарфы"},
    {"id": "armor", "label": "Броня"},
    {"id": "bg", "label": "Фон"},
    {"id": "aura", "label": "Аура"},
    {"id": "emotion", "label": "Эмоции"},
    {"id": "badge", "label": "Бейджи"},
    {"id": "effect", "label": "Редкие эффекты"},
]

CATEGORY_LABELS = {c["id"]: c["label"] for c in CATEGORIES}

RARITIES = ("common", "rare", "epic", "legendary")


class CatalogItem(TypedDict, total=False):
    item_id: str
    category: str
    name: str
    rarity: str
    unlock_condition: str | None
    starter: bool
    equip_on_start: bool
    unlock_rule: dict[str, Any] | None


def _item(
    item_id: str,
    category: str,
    name: str,
    rarity: str,
    *,
    unlock_condition: str | None = None,
    starter: bool = False,
    equip_on_start: bool = False,
    unlock_rule: dict[str, Any] | None = None,
) -> CatalogItem:
    return {
        "item_id": item_id,
        "category": category,
        "name": name,
        "rarity": rarity,
        "unlock_condition": unlock_condition,
        "starter": starter,
        "equip_on_start": equip_on_start,
        "unlock_rule": unlock_rule,
    }


PET_ITEM_CATALOG: list[CatalogItem] = [
    # --- hats ---
    _item("focus_beanie", "hat", "Beanie фокуса", "common", starter=True, equip_on_start=True),
    _item("sprint_crown", "hat", "Корона спринта", "epic",
          unlock_condition="Достигните уровня 10", unlock_rule={"type": "level", "value": 10}),
    _item("strategist_top_hat", "hat", "Цилиндр стратега", "rare",
          unlock_condition="Достигните силы команды 5000",
          unlock_rule={"type": "power", "value": 5000}),
    _item("champion_helmet", "hat", "Шлем чемпиона", "legendary",
          unlock_condition="Попадите в топ-3 месячного батла",
          unlock_rule={"type": "battle_top3"}),
    # --- glasses ---
    _item("analyst_glasses", "glasses", "Очки аналитика", "common",
          starter=True, equip_on_start=True),
    _item("vr_visor", "glasses", "VR-визор", "rare",
          unlock_condition="Достигните уровня 5", unlock_rule={"type": "level", "value": 5}),
    _item("neon_lenses", "glasses", "Неоновые линзы", "epic",
          unlock_condition="Поддерживайте статусы 7 дней подряд",
          unlock_rule={"type": "status_streak", "value": 7}),
    _item("seer_eyes", "glasses", "Очи провидца", "legendary",
          unlock_condition="Завершите неделю с высоким wellbeing",
          unlock_rule={"type": "wellbeing", "value": 80}),
    # --- scarves ---
    _item("team_scarf", "scarf", "Шарф команды", "common", starter=True),
    _item("cape_scarf", "scarf", "Плащ-шарф", "rare",
          unlock_condition="Достигните уровня 7", unlock_rule={"type": "level", "value": 7}),
    _item("harmony_silk", "scarf", "Шёлк гармонии", "epic",
          unlock_condition="Снизьте напряжение команды до низкого уровня",
          unlock_rule={"type": "low_tension", "value": 25}),
    _item("aurora_cape", "scarf", "Aurora Cape", "legendary",
          unlock_condition="Награда месяца за 1 место в батле",
          unlock_rule={"type": "battle_win"}),
    # --- armor ---
    _item("light_armor", "armor", "Лёгкий доспех", "common", starter=True),
    _item("sprinter_plate", "armor", "Латы спринтера", "rare",
          unlock_condition="Достигните уровня 8", unlock_rule={"type": "level", "value": 8}),
    _item("no_overdue_armor", "armor", "Броня без просрочек", "epic",
          unlock_condition="Закройте 30 задач без просрочки",
          unlock_rule={"type": "tasks_no_overdue", "value": 30}),
    _item("leader_aegis", "armor", "Эгида лидера", "legendary",
          unlock_condition="Удержите #1 в батле весь сезон",
          unlock_rule={"type": "battle_win"}),
    # --- backgrounds ---
    _item("studio", "bg", "Студия", "common", starter=True, equip_on_start=True),
    _item("night_city", "bg", "Ночной город", "rare",
          unlock_condition="Достигните уровня 6", unlock_rule={"type": "level", "value": 6}),
    _item("focus_space", "bg", "Космос фокуса", "epic",
          unlock_condition="Достигните силы команды 7000",
          unlock_rule={"type": "power", "value": 7000}),
    _item("aurora_bg", "bg", "Аврора", "legendary",
          unlock_condition="Достигните уровня 15", unlock_rule={"type": "level", "value": 15}),
    # --- auras ---
    _item("calm_aura", "aura", "Спокойствие", "common", starter=True, equip_on_start=True),
    _item("focus_flow", "aura", "Focus Flow", "rare",
          unlock_condition="Достигните уровня 4", unlock_rule={"type": "level", "value": 4}),
    _item("warm_support", "aura", "Тёплая поддержка", "epic",
          unlock_condition="Высокая слаженность команды",
          unlock_rule={"type": "harmony", "value": 80}),
    _item("rainbow_aura", "aura", "Радужная аура", "legendary",
          unlock_condition="Неделя с высоким wellbeing и слаженностью",
          unlock_rule={"type": "wellbeing", "value": 85}),
    # --- emotions ---
    _item("focused", "emotion", "Сфокусирован", "common", starter=True, equip_on_start=True),
    _item("joyful", "emotion", "Радостный", "common", starter=True),
    _item("battle_ready", "emotion", "Боевой настрой", "rare",
          unlock_condition="Достигните уровня 5", unlock_rule={"type": "level", "value": 5}),
    _item("zen", "emotion", "Дзен", "epic",
          unlock_condition="Держите низкое напряжение 14 дней",
          unlock_rule={"type": "low_tension", "value": 20}),
    # --- badges ---
    _item("first_blocker", "badge", "Первый блокер", "common", starter=True),
    _item("team_player", "badge", "Командный игрок", "rare",
          unlock_condition="Достигните уровня 6", unlock_rule={"type": "level", "value": 6}),
    _item("deadline_master", "badge", "Мастер дедлайнов", "epic",
          unlock_condition="30 задач вовремя подряд",
          unlock_rule={"type": "tasks_no_overdue", "value": 30}),
    _item("season_legend", "badge", "Легенда сезона", "legendary",
          unlock_condition="1 место в месячном батле",
          unlock_rule={"type": "battle_win"}),
    # --- rare effects ---
    _item("xp_sparks", "effect", "Искры XP", "rare",
          unlock_condition="Достигните уровня 9", unlock_rule={"type": "level", "value": 9}),
    _item("comet_trail", "effect", "След кометы", "epic",
          unlock_condition="Достигните силы команды 8000",
          unlock_rule={"type": "power", "value": 8000}),
    _item("star_vortex", "effect", "Звёздный вихрь", "legendary",
          unlock_condition="Откройте 25 предметов коллекции",
          unlock_rule={"type": "collection", "value": 25}),
    _item("hologram", "effect", "Голограмма", "epic",
          unlock_condition="Достигните силы команды 9000",
          unlock_rule={"type": "power", "value": 9000}),
]

CATALOG_BY_ID: dict[str, CatalogItem] = {item["item_id"]: item for item in PET_ITEM_CATALOG}

# Категория -> поле внешнего вида в TeamPetModel.
APPEARANCE_FIELD = {
    "bg": "current_background",
    "aura": "current_aura",
    "emotion": "current_emotion",
    "skin": "current_skin",
}
ACCESSORY_CATEGORIES = ("hat", "glasses", "scarf", "armor", "badge", "effect")


def starter_items() -> list[CatalogItem]:
    return [item for item in PET_ITEM_CATALOG if item.get("starter")]


def catalog_item(item_id: str) -> CatalogItem | None:
    return CATALOG_BY_ID.get(item_id)


def evaluate_unlocks(stats: dict[str, Any]) -> list[CatalogItem]:
    """Вернуть предметы каталога, чьи условия выполнены (для авто-анлока).

    ``stats`` ожидает ключи: level, power, wellbeing, harmony, tension,
    tasks_no_overdue, collection_count. Battle-предметы здесь не выдаются —
    они начисляются движком батлов.
    """
    unlocked: list[CatalogItem] = []
    for item in PET_ITEM_CATALOG:
        rule = item.get("unlock_rule")
        if not rule:
            continue
        rtype = rule.get("type")
        value = rule.get("value", 0)
        ok = False
        if rtype == "level":
            ok = stats.get("level", 0) >= value
        elif rtype == "power":
            ok = stats.get("power", 0) >= value
        elif rtype == "wellbeing":
            ok = stats.get("wellbeing", 0) >= value
        elif rtype == "harmony":
            ok = stats.get("harmony", 0) >= value
        elif rtype == "low_tension":
            ok = stats.get("tension", 100) <= value
        elif rtype == "tasks_no_overdue":
            ok = stats.get("tasks_no_overdue", 0) >= value
        elif rtype == "collection":
            ok = stats.get("collection_count", 0) >= value
        # status_streak / battle_* — выдаются отдельными движками.
        if ok:
            unlocked.append(item)
    return unlocked
