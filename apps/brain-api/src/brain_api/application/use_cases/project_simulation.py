"""Симуляция нового проекта на текущую команду (Bucket B killer-feature).

Связывает расчёт проекта (B1) + эмоции/нагрузку (B2) + питомца (B3): отвечает не
только «сколько часов и денег», но и «что проект сделает с командой» — прогноз
настроения и ёмкости на горизонте. См. docs/design/project-estimation.md.

Дизайн: чистое ядро (`simulate`) на входных work items + резолв ёмкости из БД.
Декомпозиция проекта — LLM (если настроен) с детерминированным fallback, чтобы
демо работало без сети.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.application import team_mood as tm
from brain_api.application.use_cases.team_pet import mood_inputs
from brain_api.infrastructure.db import models as m

# Ставки по ролям, ₽/час (грубые дефолты для оценки бюджета).
ROLE_RATES = {
    "backend": 3000,
    "frontend": 2800,
    "fullstack": 3200,
    "mobile": 3000,
    "design": 2500,
    "qa": 2000,
    "devops": 3500,
    "ml": 4000,
    "data": 3500,
    "pm": 2800,
    "analyst": 2600,
    "other": 2500,
}
DEFAULT_ROLE = "other"
BASE_WEEKLY_HOURS = 30.0  # продуктивных часов на человека в неделю
ACTIVE_STATUSES = ("todo", "in_progress", "blocked", "review")

# Ключевые слова → роль (для эвристической декомпозиции).
_ROLE_KEYWORDS = {
    "backend": ("api", "бэкенд", "backend", "сервер", "база", "endpoint", "интеграц"),
    "frontend": ("frontend", "фронт", "ui", "интерфейс", "верстк", "страниц", "react", "spa"),
    "mobile": ("мобильн", "android", "ios", "приложени"),
    "design": ("дизайн", "макет", "ux", "ui-кит", "прототип"),
    "qa": ("тест", "qa", "тестирован", "автотест"),
    "devops": ("деплой", "ci", "cd", "инфраструктур", "docker", "kubernetes", "девопс"),
    "ml": ("ml", "модель", "нейросет", "обучени", "ai", "llm"),
    "analyst": ("аналитик", "исследован", "требовани"),
}
# Грубая оценка часов по «весу» work item.
_HOURS_LIGHT, _HOURS_MED, _HOURS_HEAVY = 16, 40, 80
_HEAVY_HINTS = ("интеграц", "архитектур", "ml", "нейросет", "платёж", "оплат", "безопасн", "миграц")
_LIGHT_HINTS = ("правк", "мелк", "кнопк", "текст", "лог", "конфиг")


@dataclass(frozen=True)
class WorkItem:
    title: str
    role: str
    hours: float


@dataclass(frozen=True)
class MemberCapacity:
    user_id: UUID | None
    display_name: str
    role: str
    active_count: int
    stress: float
    weekly_capacity_hours: float  # эффективная, с поправкой на загрузку/стресс


@dataclass(frozen=True)
class MemberProjection:
    display_name: str
    role: str
    added_hours: float
    weeks_busy: float
    overloaded: bool


@dataclass(frozen=True)
class SimulationResult:
    verdict: str  # fits | tight | hire_needed
    horizon_weeks: int
    total_hours: float
    hours_by_role: dict[str, float]
    budget_min: int
    budget_max: int
    duration_weeks_p50: float
    duration_weeks_p90: float
    current_mood: float
    projected_mood: float
    mood_trajectory: list[float]
    missing_roles: list[str]
    member_projections: list[MemberProjection]
    risks: list[str]
    recommendations: list[str]
    work_items: list[WorkItem]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["member_projections"] = [asdict(p) for p in self.member_projections]
        data["work_items"] = [asdict(w) for w in self.work_items]
        return data


# ── Декомпозиция проекта ──────────────────────────────────────────────────────


def _detect_role(text: str) -> str:
    low = text.lower()
    for role, kws in _ROLE_KEYWORDS.items():
        if any(k in low for k in kws):
            return role
    return DEFAULT_ROLE


def _estimate_hours(text: str) -> float:
    low = text.lower()
    if any(h in low for h in _HEAVY_HINTS):
        return _HOURS_HEAVY
    if any(h in low for h in _LIGHT_HINTS):
        return _HOURS_LIGHT
    return _HOURS_MED


def heuristic_decompose(description: str) -> list[WorkItem]:
    """Детерминированная декомпозиция (fallback без LLM).

    Делит описание на пункты по строкам/«;»/«,»/«и», назначает роль и часы.
    """
    if not description or not description.strip():
        return []
    raw_parts = re.split(r"[\n;,]+|\s+и\s+", description)
    parts = [p.strip(" .-•—") for p in raw_parts if len(p.strip()) >= 4]
    if not parts:
        parts = [description.strip()]
    items: list[WorkItem] = []
    for part in parts[:12]:
        items.append(
            WorkItem(title=part[:120], role=_detect_role(part), hours=_estimate_hours(part))
        )
    return items


async def decompose_project(
    description: str,
    *,
    provider_factory: object | None = None,
    team_id: UUID | None = None,
) -> list[WorkItem]:
    """LLM-декомпозиция с graceful fallback на эвристику."""
    if provider_factory is not None and team_id is not None:
        try:
            items = await _decompose_with_llm(provider_factory, team_id, description)
            if items:
                return items
        except Exception:
            pass
    return heuristic_decompose(description)


async def _decompose_with_llm(provider_factory, team_id: UUID, description: str) -> list[WorkItem]:
    resolved = await provider_factory.resolve_for_team(team_id)
    schema = {
        "name": "project_breakdown",
        "schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "role": {"type": "string"},
                            "hours": {"type": "number"},
                        },
                        "required": ["title", "role", "hours"],
                    },
                }
            },
            "required": ["items"],
        },
    }
    prompt = (
        "Разбей проект на 3-8 рабочих задач. Для каждой: краткий title, "
        f"role (одно из: {', '.join(ROLE_RATES)}), hours (реалистичная оценка). "
        "Верни строго JSON {\"items\":[...]}.\n\nПроект:\n" + description
    )
    raw = await resolved.primary.complete_json(prompt, "project_breakdown", json_schema=schema)
    out: list[WorkItem] = []
    for it in (raw or {}).get("items", [])[:12]:
        role = str(it.get("role") or DEFAULT_ROLE).lower()
        role = role if role in ROLE_RATES else DEFAULT_ROLE
        hours = float(it.get("hours") or _HOURS_MED)
        out.append(WorkItem(title=str(it.get("title") or "Задача")[:120], role=role, hours=hours))
    return out


# ── Ёмкость команды из реальных данных ────────────────────────────────────────


async def current_capacity(
    session: AsyncSession, team_id: UUID, *, now: datetime
) -> tuple[list[MemberCapacity], float]:
    members = (
        await session.execute(
            select(m.UserModel, m.TeamMemberModel.role)
            .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
            .where(m.TeamMemberModel.team_id == team_id)
        )
    ).all()
    since = now - timedelta(days=7)
    caps: list[MemberCapacity] = []
    for user, _membership_role in members:
        active = int(
            await session.scalar(
                select(func.count()).where(
                    m.TaskModel.team_id == team_id,
                    m.TaskModel.assignee_id == user.id,
                    m.TaskModel.status.in_(ACTIVE_STATUSES),
                )
            )
            or 0
        )
        stress = float(
            await session.scalar(
                select(func.avg(m.EmotionSignalModel.stress)).where(
                    m.EmotionSignalModel.team_id == team_id,
                    m.EmotionSignalModel.user_id == user.id,
                    m.EmotionSignalModel.created_at >= since,
                )
            )
            or 0.0
        )
        role = _infer_member_role(user)
        # Эффективная ёмкость падает от текущей загрузки и стресса.
        load_factor = max(0.4, 1.0 - min(0.6, active * 0.1))
        stress_factor = max(0.4, 1.0 - 0.5 * stress)
        weekly = round(BASE_WEEKLY_HOURS * load_factor * stress_factor, 1)
        caps.append(
            MemberCapacity(
                user_id=user.id,
                display_name=user.display_name,
                role=role,
                active_count=active,
                stress=round(stress, 3),
                weekly_capacity_hours=weekly,
            )
        )
    inputs = await mood_inputs(session, team_id, now=now)
    current_mood = tm.compute_mood(inputs)
    return caps, current_mood


def _infer_member_role(user: m.UserModel) -> str:
    """Грубо вывести роль из bio/имени; иначе fullstack."""
    text = f"{user.bio or ''} {user.display_name or ''}".lower()
    for role, kws in _ROLE_KEYWORDS.items():
        if any(k in text for k in kws):
            return role
    return "fullstack"


# ── Симуляция ─────────────────────────────────────────────────────────────────


def simulate(
    work_items: list[WorkItem],
    capacities: list[MemberCapacity],
    current_mood: float,
    *,
    horizon_weeks: int = 4,
) -> SimulationResult:
    """Чистое ядро: проект × команда → бюджет, срок, прогноз настроения."""
    hours_by_role: dict[str, float] = {}
    for item in work_items:
        hours_by_role[item.role] = hours_by_role.get(item.role, 0.0) + item.hours
    total_hours = round(sum(hours_by_role.values()), 1)

    budget = sum(
        h * ROLE_RATES.get(role, ROLE_RATES[DEFAULT_ROLE])
        for role, h in hours_by_role.items()
    )
    budget_min = int(budget * 0.85)
    budget_max = int(budget * 1.3)

    team_weekly = sum(c.weekly_capacity_hours for c in capacities) or BASE_WEEKLY_HOURS
    duration_p50 = round(total_hours / team_weekly, 1) if team_weekly else 0.0
    duration_p90 = round(duration_p50 * 1.4, 1)

    # Распределяем часы по ролям на исполнителей этой роли (или fullstack/other).
    missing_roles: list[str] = []
    member_added: dict[UUID | None, float] = {}
    for role, hours in hours_by_role.items():
        matched = [c for c in capacities if c.role == role] or [
            c for c in capacities if c.role in ("fullstack", "other")
        ]
        if not matched:
            missing_roles.append(role)
            continue
        share = hours / len(matched)
        for c in matched:
            member_added[c.user_id] = member_added.get(c.user_id, 0.0) + share

    projections: list[MemberProjection] = []
    overload_pressures: list[float] = []
    for c in capacities:
        added = round(member_added.get(c.user_id, 0.0), 1)
        weeks_busy = round(added / c.weekly_capacity_hours, 1) if c.weekly_capacity_hours else 0.0
        overloaded = weeks_busy > horizon_weeks
        # Давление перегруза 0..1 относительно горизонта.
        pressure = min(1.0, weeks_busy / horizon_weeks) if horizon_weeks else 0.0
        overload_pressures.append(pressure)
        projections.append(
            MemberProjection(
                display_name=c.display_name, role=c.role, added_hours=added,
                weeks_busy=weeks_busy, overloaded=overloaded,
            )
        )

    avg_pressure = sum(overload_pressures) / len(overload_pressures) if overload_pressures else 0.0
    # Траектория настроения по неделям: давление тянет вниз, лёгкая нагрузка — восстановление.
    trajectory = [round(current_mood, 3)]
    mood = current_mood
    for _ in range(horizon_weeks):
        delta = -0.12 * avg_pressure + (0.02 if avg_pressure < 0.5 else 0.0)
        mood = max(0.0, min(1.0, mood + delta))
        trajectory.append(round(mood, 3))
    projected_mood = trajectory[-1]

    capacity_ok = total_hours <= team_weekly * horizon_weeks and not missing_roles
    if not capacity_ok or projected_mood < 0.35:
        verdict = "hire_needed"
    elif avg_pressure > 0.6 or projected_mood < 0.5 or any(p.overloaded for p in projections):
        verdict = "tight"
    else:
        verdict = "fits"

    risks = _build_risks(missing_roles, projections, capacities, projected_mood, current_mood)
    recommendations = _build_recommendations(verdict, missing_roles, projections, capacities)

    return SimulationResult(
        verdict=verdict,
        horizon_weeks=horizon_weeks,
        total_hours=total_hours,
        hours_by_role={k: round(v, 1) for k, v in hours_by_role.items()},
        budget_min=budget_min,
        budget_max=budget_max,
        duration_weeks_p50=duration_p50,
        duration_weeks_p90=duration_p90,
        current_mood=round(current_mood, 3),
        projected_mood=projected_mood,
        mood_trajectory=trajectory,
        missing_roles=missing_roles,
        member_projections=projections,
        risks=risks,
        recommendations=recommendations,
        work_items=work_items,
    )


def _build_risks(missing_roles, projections, capacities, projected_mood, current_mood) -> list[str]:
    risks: list[str] = []
    for role in missing_roles:
        risks.append(f"Нет исполнителей роли «{role}» — задачи этой роли некому взять.")
    for p in projections:
        if p.overloaded:
            risks.append(
                f"{p.display_name} перегружен(а): +{p.added_hours} ч ({p.weeks_busy} нед работы)."
            )
    for c in capacities:
        if c.stress >= 0.6:
            risks.append(
                f"{c.display_name} под стрессом ({int(c.stress*100)}%) — риск выгорания."
            )
    if projected_mood < current_mood - 0.15:
        risks.append(
            f"Настроение команды просядет с {int(current_mood*100)}% до "
            f"~{int(projected_mood*100)}% к концу горизонта."
        )
    return risks


def _build_recommendations(verdict, missing_roles, projections, capacities) -> list[str]:
    recs: list[str] = []
    for role in missing_roles:
        recs.append(f"Нанять или привлечь специалиста роли «{role}».")
    overloaded = [p for p in projections if p.overloaded]
    free = sorted(capacities, key=lambda c: c.active_count)[:1]
    if overloaded and free:
        recs.append(
            f"Перераспределить часть задач на {free[0].display_name} (наименее загружен)."
        )
    if verdict == "hire_needed":
        recs.append("Рассмотреть расширение команды или сокращение скоупа/сдвиг дедлайна.")
    elif verdict == "tight":
        recs.append("Заложить буфер по срокам (+40%) и следить за настроением команды.")
    else:
        recs.append("Текущий штаб справится — можно стартовать.")
    return recs


async def simulate_project(
    session: AsyncSession,
    team_id: UUID,
    description: str,
    *,
    horizon_weeks: int = 4,
    provider_factory: object | None = None,
    now: datetime | None = None,
) -> SimulationResult:
    """Полный сценарий: декомпозиция + ёмкость из БД + симуляция."""
    now = now or datetime.now(UTC)
    work_items = await decompose_project(
        description, provider_factory=provider_factory, team_id=team_id
    )
    capacities, current_mood = await current_capacity(session, team_id, now=now)
    return simulate(work_items, capacities, current_mood, horizon_weeks=max(1, horizon_weeks))


VERDICT_LABEL = {
    "fits": "✅ Команда справится",
    "tight": "⚠️ На грани",
    "hire_needed": "🛑 Нужно усиление",
}


def render_simulation_text(result: SimulationResult, *, project_name: str = "проект") -> str:
    """Краткий рендер для чата Telegram (HTML)."""
    lines = [
        f"🧮 <b>Расчёт: {project_name}</b>",
        f"{VERDICT_LABEL.get(result.verdict, result.verdict)}",
        "",
        f"Объём: {result.total_hours:.0f} ч · "
        f"Бюджет: {result.budget_min:,}–{result.budget_max:,} ₽".replace(",", " "),
        f"Срок: ~{result.duration_weeks_p50} нед (P90 {result.duration_weeks_p90} нед)",
        f"Настроение команды: {int(result.current_mood*100)}% → "
        f"{int(result.projected_mood*100)}% к неделе {result.horizon_weeks}",
    ]
    if result.missing_roles:
        lines.append(f"Не хватает ролей: {', '.join(result.missing_roles)}")
    if result.risks:
        lines.append("\n<b>Риски:</b>")
        lines += [f"• {r}" for r in result.risks[:4]]
    if result.recommendations:
        lines.append("\n<b>Рекомендации:</b>")
        lines += [f"• {r}" for r in result.recommendations[:3]]
    return "\n".join(lines)
