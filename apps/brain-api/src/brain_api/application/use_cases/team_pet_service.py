"""Высокоуровневые операции командного питомца (поверх team_pet/scoring/catalog).

Содержит: privacy-настройки, инвентарь и экипировку, событийный фид, авто-анлок,
создание/переименование питомца и сборку расширенного payload под новый frontend.
Не ломает legacy: расширенный payload включает старые поля верхнего уровня.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application import pet_catalog as cat
from brain_api.application import team_mood as tm
from brain_api.application.use_cases import team_pet as tp
from brain_api.application.use_cases import team_pet_scoring as sc
from brain_api.infrastructure.db import models as m

SPECIES = {
    "fox": ("Лисёнок-стратег", "🦊"),
    "capybara": ("Капибара гармонии", "🦫"),
    "dragon": ("Дракончик энергии", "🐲"),
    "owl": ("Сова фокуса", "🦉"),
}
VALID_SPECIES = tuple(SPECIES.keys())

_MOOD_LABEL = {
    "happy": ("happy", "Счастлив"),
    "content": ("content", "Доволен"),
    "neutral": ("neutral", "Спокоен"),
    "tired": ("tired", "Устал"),
    "sad": ("sad", "Загрустил"),
}

# Лимиты throttling событий (в секундах).
_NEG_COMM_THROTTLE = timedelta(hours=6)
_POS_CHAT_THROTTLE = timedelta(hours=2)

DEFAULT_PRIVACY = {
    "analyze_tasks": True,
    "analyze_chat": False,
    "analyze_calls": False,
    "analyze_camera": False,
    "team_aggregates_only": True,
    "manager_individual_signals": False,
    "retention_days": 30,
    "visible_to": "managers",
}


# ── Privacy ──────────────────────────────────────────────────────────────────


async def ensure_privacy(session: AsyncSession, team_id: UUID) -> m.TeamPetPrivacyModel:
    row = await session.scalar(
        select(m.TeamPetPrivacyModel).where(m.TeamPetPrivacyModel.team_id == team_id)
    )
    if row is None:
        # Унаследовать opt-in анализа чата из team.board_config, если он есть.
        analyze_chat = DEFAULT_PRIVACY["analyze_chat"]
        team = await session.get(m.TeamModel, team_id)
        if team is not None and isinstance(team.board_config, dict):
            analyze_chat = bool(team.board_config.get("emotion_analysis", analyze_chat))
        row = m.TeamPetPrivacyModel(team_id=team_id, analyze_chat=analyze_chat)
        session.add(row)
        await session.flush()
    return row


def privacy_dict(row: m.TeamPetPrivacyModel) -> dict[str, Any]:
    return {
        "analyze_tasks": row.analyze_tasks,
        "analyze_chat": row.analyze_chat,
        "analyze_calls": row.analyze_calls,
        "analyze_camera": row.analyze_camera,
        "team_aggregates_only": row.team_aggregates_only,
        "manager_individual_signals": row.manager_individual_signals,
        "retention_days": row.retention_days,
        "visible_to": row.visible_to,
    }


async def update_privacy(
    session: AsyncSession,
    team_id: UUID,
    data: dict[str, Any],
    *,
    can_enable_sensitive: bool,
) -> m.TeamPetPrivacyModel:
    row = await ensure_privacy(session, team_id)
    if "analyze_tasks" in data:
        row.analyze_tasks = bool(data["analyze_tasks"])
    if "analyze_chat" in data:
        row.analyze_chat = bool(data["analyze_chat"])
    if "team_aggregates_only" in data:
        row.team_aggregates_only = bool(data["team_aggregates_only"])
    if "manager_individual_signals" in data:
        row.manager_individual_signals = bool(data["manager_individual_signals"])
    if "retention_days" in data:
        row.retention_days = max(1, int(data["retention_days"]))
    if "visible_to" in data and data["visible_to"] in ("managers", "team", "admins"):
        row.visible_to = data["visible_to"]
    # calls/camera — только manager/director/admin может включить.
    if can_enable_sensitive:
        if "analyze_calls" in data:
            row.analyze_calls = bool(data["analyze_calls"])
        if "analyze_camera" in data:
            row.analyze_camera = bool(data["analyze_camera"])
    else:
        row.analyze_calls = False
        row.analyze_camera = False
    await session.flush()
    return row


async def cleanup_old_signals(session: AsyncSession, team_id: UUID, *, now: datetime) -> int:
    """Удалить emotion_signals старше retention_days (privacy). Возвращает счётчик."""
    row = await ensure_privacy(session, team_id)
    cutoff = now - timedelta(days=row.retention_days)
    old = (
        (
            await session.execute(
                select(m.EmotionSignalModel).where(
                    m.EmotionSignalModel.team_id == team_id,
                    m.EmotionSignalModel.created_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    for signal in old:
        await session.delete(signal)
    return len(old)


# ── Inventory ────────────────────────────────────────────────────────────────


async def _inventory_rows(
    session: AsyncSession, team_id: UUID
) -> dict[str, m.TeamPetInventoryModel]:
    rows = (
        (
            await session.execute(
                select(m.TeamPetInventoryModel).where(
                    m.TeamPetInventoryModel.team_id == team_id
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.item_id: row for row in rows}


async def grant_item(
    session: AsyncSession,
    team_id: UUID,
    item_id: str,
    *,
    status: str = "owned",
    reason: str | None = None,
    now: datetime | None = None,
) -> m.TeamPetInventoryModel | None:
    item = cat.catalog_item(item_id)
    if item is None:
        return None
    now = now or datetime.now(UTC)
    row = await session.scalar(
        select(m.TeamPetInventoryModel).where(
            m.TeamPetInventoryModel.team_id == team_id,
            m.TeamPetInventoryModel.item_id == item_id,
        )
    )
    if row is None:
        row = m.TeamPetInventoryModel(
            team_id=team_id,
            item_id=item_id,
            item_type=item["category"],
            rarity=item["rarity"],
            status=status,
            unlocked_at=now if status in ("owned", "equipped") else None,
            unlock_reason=reason,
        )
        session.add(row)
    elif row.status == "locked" and status in ("owned", "equipped"):
        row.status = status
        row.unlocked_at = now
        row.unlock_reason = reason
    await session.flush()
    return row


async def list_inventory(session: AsyncSession, team_id: UUID) -> dict[str, Any]:
    """Слить каталог с состоянием БД: каталог — locked по умолчанию."""
    rows = await _inventory_rows(session, team_id)
    items: list[dict[str, Any]] = []
    owned_count = 0
    for entry in cat.PET_ITEM_CATALOG:
        row = rows.get(entry["item_id"])
        status = row.status if row else "locked"
        if status in ("owned", "equipped"):
            owned_count += 1
        items.append(
            {
                "item_id": entry["item_id"],
                "category": entry["category"],
                "name": entry["name"],
                "rarity": entry["rarity"],
                "status": status,
                "unlock_condition": entry.get("unlock_condition"),
            }
        )
    return {
        "categories": cat.CATEGORIES,
        "items": items,
        "owned_count": owned_count,
        "total_count": len(cat.PET_ITEM_CATALOG),
    }


def _apply_appearance(pet: m.TeamPetModel, item: cat.CatalogItem) -> None:
    category = item["category"]
    item_id = item["item_id"]
    if category == "bg":
        pet.current_background = item_id
    elif category == "aura":
        pet.current_aura = item_id
    elif category == "emotion":
        pet.current_emotion = item_id
    elif category == "skin":
        pet.current_skin = item_id
    else:  # аксессуары: hat/glasses/scarf/armor/badge/effect
        acc = dict(pet.current_accessories or {})
        acc[category] = item_id
        pet.current_accessories = acc


async def equip_item(
    session: AsyncSession, team_id: UUID, item_id: str, *, now: datetime | None = None
) -> tuple[bool, str]:
    """Надеть предмет. Возвращает (ok, message/category)."""
    now = now or datetime.now(UTC)
    item = cat.catalog_item(item_id)
    if item is None:
        return False, "unknown_item"
    row = await session.scalar(
        select(m.TeamPetInventoryModel).where(
            m.TeamPetInventoryModel.team_id == team_id,
            m.TeamPetInventoryModel.item_id == item_id,
        )
    )
    if row is None or row.status == "locked":
        return False, "locked"
    category = item["category"]
    # Снять остальные надетые в этой категории.
    same_cat = (
        (
            await session.execute(
                select(m.TeamPetInventoryModel).where(
                    m.TeamPetInventoryModel.team_id == team_id,
                    m.TeamPetInventoryModel.item_type == category,
                    m.TeamPetInventoryModel.status == "equipped",
                )
            )
        )
        .scalars()
        .all()
    )
    for other in same_cat:
        if other.item_id != item_id:
            other.status = "owned"
            other.equipped_at = None
    row.status = "equipped"
    row.equipped_at = now
    pet = await tp.ensure_pet(session, team_id)
    _apply_appearance(pet, item)
    await record_event(
        session,
        pet,
        event_type="item_equipped",
        metric="mood",
        points_delta=0,
        reason=f"Надет предмет: {item['name']}",
        source_type="manual",
        metadata={"item_id": item_id, "category": category},
        now=now,
    )
    await session.flush()
    return True, category


# ── Events ───────────────────────────────────────────────────────────────────


async def record_event(
    session: AsyncSession,
    pet: m.TeamPetModel,
    *,
    event_type: str,
    metric: str,
    points_delta: int,
    reason: str,
    source_type: str | None = None,
    source_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> m.TeamPetEventModel:
    now = now or datetime.now(UTC)
    event = m.TeamPetEventModel(
        team_id=pet.team_id,
        pet_id=pet.id,
        event_type=event_type,
        source_type=source_type,
        source_id=source_id,
        points_delta=points_delta,
        metric=metric,
        reason=reason,
        metadata_json=metadata,
        created_at=now,
    )
    session.add(event)
    await session.flush()
    return event


async def _recent_event_exists(
    session: AsyncSession,
    team_id: UUID,
    event_types: tuple[str, ...],
    within: timedelta,
    now: datetime,
) -> bool:
    since = now - within
    found = await session.scalar(
        select(m.TeamPetEventModel.id)
        .where(
            m.TeamPetEventModel.team_id == team_id,
            m.TeamPetEventModel.event_type.in_(event_types),
            m.TeamPetEventModel.created_at >= since,
        )
        .limit(1)
    )
    return found is not None


def _event_delta_label(metric: str, points_delta: int) -> str:
    sign = "+" if points_delta >= 0 else "−"
    magnitude = abs(points_delta)
    if metric == "xp":
        return f"{sign}{magnitude} XP"
    return f"{sign}{magnitude}"


async def list_events(
    session: AsyncSession,
    team_id: UUID,
    *,
    limit: int = 30,
    cursor: str | None = None,
) -> dict[str, Any]:
    query = select(m.TeamPetEventModel).where(m.TeamPetEventModel.team_id == team_id)
    if cursor:
        try:
            cutoff = datetime.fromisoformat(cursor)
            query = query.where(m.TeamPetEventModel.created_at < cutoff)
        except ValueError:
            pass
    query = query.order_by(desc(m.TeamPetEventModel.created_at)).limit(limit + 1)
    rows = (await session.execute(query)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = []
    for row in rows:
        meta = ""
        if isinstance(row.metadata_json, dict):
            meta = str(row.metadata_json.get("meta", ""))
        if not meta and row.source_type:
            meta = {"task": "из задач", "chat_message": "из чата", "wellbeing": "wellbeing",
                    "battle": "батл", "system": "система", "manual": "вручную"}.get(
                        row.source_type, row.source_type)
        items.append(
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "delta": _event_delta_label(row.metric, row.points_delta),
                "points_delta": row.points_delta,
                "positive": row.points_delta >= 0,
                "metric": row.metric,
                "title": row.reason,
                "meta": meta,
                "created_at": _iso(row.created_at),
            }
        )
    next_cursor = _iso(rows[-1].created_at) if (has_more and rows) else None
    return {"items": items, "next_cursor": next_cursor}


# ── Auto-unlocks ─────────────────────────────────────────────────────────────


async def process_unlocks(
    session: AsyncSession,
    pet: m.TeamPetModel,
    scores: sc.Scores,
    inputs: sc.ScoringInputs,
    *,
    now: datetime,
) -> list[str]:
    """Выдать новые предметы, чьи условия выполнены. Возвращает item_ids."""
    rows = await _inventory_rows(session, pet.team_id)
    owned_count = sum(1 for r in rows.values() if r.status in ("owned", "equipped"))
    stats = {
        "level": pet.level,
        "power": pet.power_score,
        "wellbeing": scores.wellbeing,
        "harmony": scores.harmony,
        "tension": scores.tension,
        "tasks_no_overdue": inputs.done_no_overdue,
        "collection_count": owned_count,
    }
    newly: list[str] = []
    for item in cat.evaluate_unlocks(stats):
        existing = rows.get(item["item_id"])
        if existing is not None and existing.status != "locked":
            continue
        await grant_item(
            session,
            pet.team_id,
            item["item_id"],
            status="owned",
            reason=item.get("unlock_condition"),
            now=now,
        )
        await record_event(
            session,
            pet,
            event_type="item_unlocked",
            metric="xp",
            points_delta=0,
            reason=f"Открыт предмет: {item['name']}",
            source_type="system",
            metadata={"item_id": item["item_id"], "meta": "новая награда"},
            now=now,
        )
        newly.append(item["item_id"])
    return newly


# ── Event generation hooks (task close / chat affect) ────────────────────────


async def chat_analysis_allowed(session: AsyncSession, team_id: UUID) -> bool:
    """True, если privacy команды разрешает анализ чата.

    Если строки privacy ещё нет — не блокируем (управляет legacy team opt-in).
    """
    row = await session.scalar(
        select(m.TeamPetPrivacyModel).where(m.TeamPetPrivacyModel.team_id == team_id)
    )
    if row is None:
        return True
    return row.analyze_chat


async def task_analysis_allowed(session: AsyncSession, team_id: UUID) -> bool:
    row = await session.scalar(
        select(m.TeamPetPrivacyModel).where(m.TeamPetPrivacyModel.team_id == team_id)
    )
    if row is None:
        return True
    return row.analyze_tasks


async def feed_pet_event(
    session: AsyncSession,
    team_id: UUID,
    *,
    kind: str,
    points: int,
    task_id: UUID | None = None,
    now: datetime | None = None,
) -> None:
    """Покормить питомца и записать событие за позитивное действие команды.

    Не создаёт питомца, если его ещё нет (уважение к create/empty state).
    Уважает privacy.analyze_tasks для task-событий.
    """
    now = now or datetime.now(UTC)
    if not await pet_exists(session, team_id):
        return
    task_related = kind == "task_completed"
    if task_related and not await task_analysis_allowed(session, team_id):
        return
    xp_gain = max(1, points // 2)
    pet = await tp.feed_pet(session, team_id, energy_gain=0.1, xp_gain=xp_gain, now=now)

    event_type = "status_report_sent"
    metric = "xp"
    reason = "Команда выполнила полезное действие"
    meta = "авто"
    if task_related and task_id is not None:
        task = await session.get(m.TaskModel, task_id)
        on_time = True
        if task is not None and task.deadline is not None and task.completed_at is not None:
            on_time = _as_utc(task.completed_at) <= _as_utc(task.deadline)
        if on_time:
            event_type = "task_completed_on_time"
            reason = "Задача закрыта вовремя"
        else:
            event_type = "task_completed_late"
            reason = "Задача закрыта с просрочкой"
        meta = "из задач"
    elif kind == "risk_resolved":
        event_type = "blocker_resolved"
        metric = "harmony"
        reason = "Команда закрыла блокер"
        meta = "wellbeing"
    elif kind in ("meeting_summary_ready", "meeting_joined"):
        event_type = "status_report_sent"
        reason = "Команда синхронизировалась на созвоне"
        meta = "созвоны"

    await record_event(
        session,
        pet,
        event_type=event_type,
        metric=metric,
        points_delta=xp_gain,
        reason=reason,
        source_type="task" if task_related else "system",
        source_id=task_id,
        metadata={"meta": meta},
        now=now,
    )


async def on_chat_affect(
    session: AsyncSession,
    team_id: UUID,
    *,
    valence: float,
    stress: float,
    source_id: UUID | None = None,
    now: datetime | None = None,
) -> None:
    """Сгенерировать throttled communication-событие из эмоционального сигнала чата."""
    now = now or datetime.now(UTC)
    if not await pet_exists(session, team_id):
        return
    pet = await tp.ensure_pet(session, team_id)
    if valence <= -0.35 or stress >= 0.6:
        if await _recent_event_exists(
            session, team_id, ("toxicity_signal", "stress_signal"), _NEG_COMM_THROTTLE, now
        ):
            return
        if stress >= 0.6:
            event_type, metric, reason = ("stress_signal", "wellbeing", "Выросло напряжение в чате")
        else:
            event_type, metric, reason = (
                "toxicity_signal",
                "communication",
                "Тон коммуникации стал жёстче",
            )
        await record_event(
            session,
            pet,
            event_type=event_type,
            metric=metric,
            points_delta=-10,
            reason=reason,
            source_type="chat_message",
            source_id=source_id,
            metadata={"meta": "из чата"},
            now=now,
        )
    elif valence >= 0.5:
        if await _recent_event_exists(
            session, team_id, ("helpful_message",), _POS_CHAT_THROTTLE, now
        ):
            return
        await record_event(
            session,
            pet,
            event_type="helpful_message",
            metric="harmony",
            points_delta=15,
            reason="Поддержка и помощь в чате",
            source_type="chat_message",
            source_id=source_id,
            metadata={"meta": "из чата · +Harmony"},
            now=now,
        )


# ── Create / rename ──────────────────────────────────────────────────────────


async def pet_exists(session: AsyncSession, team_id: UUID) -> bool:
    found = await session.scalar(
        select(m.TeamPetModel.id).where(m.TeamPetModel.team_id == team_id)
    )
    return found is not None


async def create_pet(
    session: AsyncSession,
    team_id: UUID,
    *,
    name: str,
    species: str,
    now: datetime | None = None,
) -> m.TeamPetModel:
    now = now or datetime.now(UTC)
    species = species if species in VALID_SPECIES else "fox"
    pet = m.TeamPetModel(
        team_id=team_id,
        name=name.strip()[:40] or "Кардиналыч",
        species=species,
        last_decay_at=now,
    )
    session.add(pet)
    await session.flush()
    # Стартовый инвентарь + экипировка.
    for item in cat.starter_items():
        status = "equipped" if item.get("equip_on_start") else "owned"
        await grant_item(
            session, team_id, item["item_id"], status=status, reason="starter", now=now
        )
        if status == "equipped":
            _apply_appearance(pet, item)
    await ensure_privacy(session, team_id)
    await record_event(
        session,
        pet,
        event_type="pet_created",
        metric="xp",
        points_delta=0,
        reason=f"Питомец создан: {pet.name}",
        source_type="manual",
        metadata={"species": species, "meta": "создание питомца"},
        now=now,
    )
    await session.flush()
    return pet


async def rename_pet(
    session: AsyncSession, team_id: UUID, *, name: str, now: datetime | None = None
) -> m.TeamPetModel:
    now = now or datetime.now(UTC)
    pet = await tp.ensure_pet(session, team_id)
    old = pet.name
    pet.name = name.strip()[:40] or pet.name
    await record_event(
        session,
        pet,
        event_type="pet_renamed",
        metric="xp",
        points_delta=0,
        reason=f"Питомец переименован: {old} → {pet.name}",
        source_type="manual",
        now=now,
    )
    await session.flush()
    return pet


# ── Payload ──────────────────────────────────────────────────────────────────


async def _rank(session: AsyncSession, pet: m.TeamPetModel) -> int | None:
    higher = await session.scalar(
        select(func.count()).where(m.TeamPetModel.power_score > pet.power_score)
    )
    total = await session.scalar(select(func.count()).where(m.TeamPetModel.id.is_not(None)))
    if not total or total <= 1:
        return None
    return int(higher or 0) + 1


def _appearance(pet: m.TeamPetModel) -> dict[str, Any]:
    return {
        "skin": pet.current_skin or "default",
        "background": pet.current_background or "studio",
        "aura": pet.current_aura,
        "emotion": pet.current_emotion or "focused",
        "accessories": dict(pet.current_accessories or {}),
    }


async def build_pet_payload(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> dict[str, Any]:
    """Расширенный payload под новый frontend (включает legacy-поля)."""
    now = now or datetime.now(UTC)
    privacy = await ensure_privacy(session, team_id)
    # Базовый питомец + decay + mood (legacy).
    pet = await tp.recompute_pet(session, team_id, now=now)
    scores, prev, inputs = await sc.recompute_scores(
        session,
        pet,
        now=now,
        analyze_tasks=privacy.analyze_tasks,
        analyze_chat=privacy.analyze_chat,
    )
    await process_unlocks(session, pet, scores, inputs, now=now)

    state = tm.pet_state(pet.mood, pet.energy)
    mood_key, mood_label = _MOOD_LABEL.get(state, ("neutral", "Спокоен"))
    species_name, emoji = SPECIES.get(pet.species, SPECIES["fox"])
    level_floor = (pet.level - 1) * 100
    xp_next = pet.level * 100
    rank = await _rank(session, pet)

    legacy_breakdown = {
        "emotion_valence": inputs.emotion_valence,
        "emotion_stress": inputs.emotion_stress,
        "task_health": round(1.0 - inputs.overdue_pressure, 3),
        "overdue_pressure": round(inputs.overdue_pressure, 3),
        "activity": round(inputs.activity, 3),
        "emotion_available": inputs.emotion_count > 0,
    }

    return {
        "team_id": str(team_id),
        # --- legacy top-level fields (бот/mini-app) ---
        "name": pet.name,
        "species": pet.species,
        "mood": pet.mood,
        "energy": pet.energy,
        "level": pet.level,
        "xp": pet.xp,
        "state": state,
        "emoji": emoji,
        "phrase": tm.state_phrase(state),
        "breakdown": legacy_breakdown,
        # --- extended ---
        "pet": {
            "id": str(pet.id),
            "name": pet.name,
            "species": pet.species,
            "species_name": species_name,
            "level": pet.level,
            "xp": pet.xp,
            "xp_floor": level_floor,
            "xp_next": xp_next,
            "mood": mood_key,
            "mood_label": mood_label,
            "energy": pet.energy,
            "power_score": round(pet.power_score),
            "rank": rank,
            "state": state,
            "emoji": emoji,
            "phrase": tm.state_phrase(state),
        },
        "appearance": _appearance(pet),
        "scores": scores.as_dict(),
        "metrics": sc.build_metric_cards(scores, prev),
        "privacy": privacy_dict(privacy),
        "updated_at": _iso(now),
    }


# ── Wellbeing aggregates ─────────────────────────────────────────────────────


async def wellbeing_payload(
    session: AsyncSession, team_id: UUID, *, include_individual: bool, now: datetime | None = None
) -> dict[str, Any]:
    """Агрегаты wellbeing без публичного shame. Индивидуальные данные — опционально."""
    from brain_api.application.use_cases.agentic_wellbeing import (
        _member_loads,
        detect_interventions,
    )

    now = now or datetime.now(UTC)
    privacy = await ensure_privacy(session, team_id)
    pet = await tp.ensure_pet(session, team_id)
    scores, _prev, inputs = await sc.recompute_scores(
        session,
        pet,
        now=now,
        analyze_tasks=privacy.analyze_tasks,
        analyze_chat=privacy.analyze_chat,
    )
    loads = await _member_loads(session, team_id, now=now)
    at_risk = sum(1 for load in loads if load.at_risk)
    overload = round(100 * inputs.overdue_pressure + 20 * (at_risk / max(1, len(loads))))

    def color(value: float, *, invert: bool = False) -> str:
        v = 100 - value if invert else value
        return "ok" if v >= 66 else "warn" if v >= 40 else "err"

    def band(value: float, low: str, mid: str, high: str) -> str:
        return low if value < 33 else mid if value < 66 else high

    cards = [
        {
            "key": "overload",
            "label": "Уровень перегруза",
            "status": band(overload, "низкий", "умеренный", "высокий"),
            "status_color": color(100 - overload),
            "value": int(min(100, overload)),
            "explanation": (
                "Нагрузка распределена ровно."
                if overload < 33
                else "У части участников выросла нагрузка — стоит перераспределить задачи."
            ),
        },
        {
            "key": "communication_tone",
            "label": "Тон коммуникации",
            "status": "спокойный" if scores.communication >= 66 else "напряжённый",
            "status_color": color(scores.communication),
            "value": int(scores.communication),
            "explanation": "Коммуникация спокойная." if scores.communication >= 66
            else "Тон коммуникации стоит мягко выровнять.",
        },
        {
            "key": "load_balance",
            "label": "Баланс нагрузки",
            "status": "хороший" if scores.harmony >= 66 else "неравномерный",
            "status_color": color(scores.harmony),
            "value": int(scores.harmony),
            "explanation": "Задачи распределены ровно." if scores.harmony >= 66
            else "Нагрузка распределена неравномерно.",
        },
        {
            "key": "burnout_risk",
            "label": "Риск выгорания",
            "status": band(scores.tension, "низкий", "умеренный", "высокий"),
            "status_color": color(scores.tension, invert=True),
            "value": int(scores.tension),
            "explanation": "Риск выгорания низкий." if scores.tension < 33
            else "Есть риск из-за нагрузки и напряжения.",
        },
        {
            "key": "wellbeing",
            "label": "Wellbeing команды",
            "status": "в норме" if scores.wellbeing >= 66 else "под риском",
            "status_color": color(scores.wellbeing),
            "value": int(scores.wellbeing),
            "explanation": "Баланс в норме." if scores.wellbeing >= 66
            else "Есть риск перегруза у части участников.",
        },
        {
            "key": "stability",
            "label": "Регулярность работы",
            "status": "стабильно" if scores.stability >= 66 else "нестабильно",
            "status_color": color(scores.stability),
            "value": int(scores.stability),
            "explanation": "Процесс ровный." if scores.stability >= 66
            else "Процесс нестабилен.",
        },
    ]

    interventions_raw = await detect_interventions(session, team_id, now=now)
    interventions = [
        {
            "kind": iv.kind,
            "summary": (
                f"Есть риск перегруза ({iv.reason})"
                if iv.kind == "reassign_overload"
                else f"Стоит обратить внимание: {iv.reason}"
            ),
            "severity": "high" if "стресс" in iv.reason else "medium",
            "action_label": "Посмотреть задачи" if iv.task_public_id else "Открыть команду",
        }
        for iv in interventions_raw
    ]

    payload: dict[str, Any] = {
        "team_id": str(team_id),
        "cards": cards,
        "interventions": interventions,
        "scores": scores.as_dict(),
        "privacy": privacy_dict(privacy),
        "analysis_enabled": privacy.analyze_tasks or privacy.analyze_chat,
    }
    # Индивидуальные сигналы — только если разрешено и запрошено manager+.
    show_individual = (
        include_individual
        and privacy.manager_individual_signals
        and not privacy.team_aggregates_only
    )
    if show_individual:
        payload["members"] = [
            {
                "user_id": str(load.user_id),
                "display_name": load.display_name,
                "active_count": load.active_count,
                "overdue_count": load.overdue_count,
                "stress": load.stress,
                "at_risk": load.at_risk,
            }
            for load in loads
        ]
    return payload


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
