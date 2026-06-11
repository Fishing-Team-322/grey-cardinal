"""Месячный батл команд: ранжирование питомцев по силе команды.

Батл — это дружеское соревнование. Лидерборд строится по ``power_score`` питомцев
и не раскрывает приватные wellbeing-данные. Победитель получает legendary-предмет.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application import pet_catalog as cat
from brain_api.application.use_cases import team_pet_scoring as sc
from brain_api.infrastructure.db import models as m

DEFAULT_REWARD_ITEM = "aurora_cape"


def _period(now: datetime) -> str:
    return now.strftime("%Y-%m")


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    if now.month == 12:
        next_start = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        next_start = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    return start, next_start


async def ensure_current_battle(
    session: AsyncSession, *, now: datetime | None = None
) -> m.TeamBattleModel:
    now = now or datetime.now(UTC)
    period = _period(now)
    battle = await session.scalar(
        select(m.TeamBattleModel).where(m.TeamBattleModel.period == period)
    )
    if battle is None:
        start, next_start = _month_bounds(now)
        battle = m.TeamBattleModel(
            period=period,
            starts_at=start,
            ends_at=next_start,
            status="active",
            reward_item_id=DEFAULT_REWARD_ITEM,
        )
        session.add(battle)
        await session.flush()
    return battle


async def _refresh_scores(
    session: AsyncSession, battle: m.TeamBattleModel, *, now: datetime
) -> list[m.TeamBattleScoreModel]:
    """Пересчитать силу всех команд с питомцем и обновить снимок батла."""
    pets = (await session.execute(select(m.TeamPetModel))).scalars().all()
    existing = {
        row.team_id: row
        for row in (
            await session.execute(
                select(m.TeamBattleScoreModel).where(
                    m.TeamBattleScoreModel.battle_id == battle.id
                )
            )
        ).scalars().all()
    }
    for pet in pets:
        privacy = await session.scalar(
            select(m.TeamPetPrivacyModel).where(m.TeamPetPrivacyModel.team_id == pet.team_id)
        )
        analyze_tasks = privacy.analyze_tasks if privacy else True
        analyze_chat = privacy.analyze_chat if privacy else False
        scores, _prev, _inp = await sc.recompute_scores(
            session, pet, now=now, analyze_tasks=analyze_tasks, analyze_chat=analyze_chat
        )
        row = existing.get(pet.team_id)
        if row is None:
            row = m.TeamBattleScoreModel(
                battle_id=battle.id,
                team_id=pet.team_id,
                pet_id=pet.id,
                power_score=scores.power,
            )
            session.add(row)
            existing[pet.team_id] = row
        else:
            row.power_score = scores.power
            row.pet_id = pet.id
    await session.flush()
    # Ранжирование.
    ranked = sorted(existing.values(), key=lambda r: r.power_score, reverse=True)
    for index, row in enumerate(ranked, start=1):
        row.rank = index
    await session.flush()
    return ranked


def _reward_label(item_id: str | None) -> str | None:
    if not item_id:
        return None
    item = cat.catalog_item(item_id)
    if item is None:
        return item_id
    return f"{item['rarity'].title()} {item['name']}"


async def current_battle_payload(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, object]:
    now = now or datetime.now(UTC)
    battle = await ensure_current_battle(session, now=now)
    days_left = max(0, (_as_utc(battle.ends_at) - now).days)
    return {
        "battle": {
            "id": str(battle.id),
            "period": battle.period,
            "starts_at": _iso(battle.starts_at),
            "ends_at": _iso(battle.ends_at),
            "days_left": days_left,
            "status": battle.status,
            "reward_item_id": battle.reward_item_id,
            "reward_label": _reward_label(battle.reward_item_id),
        }
    }


async def leaderboard_payload(
    session: AsyncSession,
    *,
    current_team_id: UUID | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    now = now or datetime.now(UTC)
    battle = await ensure_current_battle(session, now=now)
    ranked = await _refresh_scores(session, battle, now=now)
    days_left = max(0, (_as_utc(battle.ends_at) - now).days)

    items = []
    for row in ranked:
        team = await session.get(m.TeamModel, row.team_id)
        pet = await session.scalar(
            select(m.TeamPetModel).where(m.TeamPetModel.team_id == row.team_id)
        )
        from brain_api.application.use_cases.team_pet_service import SPECIES

        species = pet.species if pet else "fox"
        species_name = SPECIES.get(species, SPECIES["fox"])[0]
        reward = None
        if row.rank == 1:
            reward = _reward_label(battle.reward_item_id)
        elif row.rank and row.rank <= 3:
            reward = "Эпик-награда"
        items.append(
            {
                "rank": row.rank,
                "team_id": str(row.team_id),
                "team_name": team.name if team else "Команда",
                "pet": {
                    "name": pet.name if pet else "Питомец",
                    "species": species,
                    "species_name": species_name,
                },
                "power_score": row.power_score,
                "streak": f"{row.streak} побед" if row.streak else "—",
                "reward": reward or "—",
                "is_current_team": current_team_id is not None
                and row.team_id == current_team_id,
            }
        )

    return {
        "battle": {
            "id": str(battle.id),
            "period": battle.period,
            "ends_at": _iso(battle.ends_at),
            "days_left": days_left,
            "reward_item_id": battle.reward_item_id,
            "reward_label": _reward_label(battle.reward_item_id),
        },
        "items": items,
    }


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
