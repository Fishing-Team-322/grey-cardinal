"""Агентный контур заботы о команде (Bucket B differentiator).

Связывает эмоциональный портрет + загрузку задач и ПРОАКТИВНО предлагает
интервенции: перебросить задачу с перегруженного/выгорающего сотрудника на
более свободного — переиспользуя инфраструктуру переброса из Bucket A
(PendingChatActionModel + подтверждение менеджера/директора).

См. docs/design/emotional-portrait.md и gamification-tamagotchi.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.infrastructure.db import models as m

ACTIVE_STATUSES = ("todo", "in_progress", "blocked", "review")
STRESS_WINDOW_DAYS = 7

# Пороги риска.
RISK_OVERDUE = 2          # ≥2 просрочки → риск
RISK_STRESS = 0.6         # средний стресс ≥0.6 → риск
MIN_ACTIVE_FOR_RISK = 2   # риск считаем только при реальной загрузке
LOAD_GAP = 2              # кандидат должен быть ощутимо свободнее


@dataclass(frozen=True)
class MemberLoad:
    user_id: UUID
    display_name: str
    telegram_user_id: int | None
    active_count: int
    overdue_count: int
    stress: float

    @property
    def load_score(self) -> float:
        return self.active_count + 2 * self.overdue_count + 3 * self.stress

    @property
    def at_risk(self) -> bool:
        return self.active_count >= MIN_ACTIVE_FOR_RISK and (
            self.overdue_count >= RISK_OVERDUE or self.stress >= RISK_STRESS
        )


@dataclass(frozen=True)
class Intervention:
    kind: str                      # 'reassign_overload' | 'suggest_pause'
    at_risk: MemberLoad
    candidate: MemberLoad | None
    task_id: UUID | None
    task_public_id: str | None
    task_title: str | None
    reason: str


async def _member_loads(
    session: AsyncSession, team_id: UUID, *, now: datetime
) -> list[MemberLoad]:
    members = (
        await session.execute(
            select(m.UserModel)
            .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
            .where(m.TeamMemberModel.team_id == team_id)
        )
    ).scalars().all()
    since = now - timedelta(days=STRESS_WINDOW_DAYS)
    loads: list[MemberLoad] = []
    for user in members:
        active = (
            await session.execute(
                select(m.TaskModel).where(
                    m.TaskModel.team_id == team_id,
                    m.TaskModel.assignee_id == user.id,
                    m.TaskModel.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalars().all()
        overdue = sum(
            1 for t in active if t.deadline is not None and _as_utc(t.deadline) < now
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
        loads.append(
            MemberLoad(
                user_id=user.id,
                display_name=user.display_name,
                telegram_user_id=user.telegram_user_id,
                active_count=len(active),
                overdue_count=overdue,
                stress=round(stress, 3),
            )
        )
    return loads


async def _movable_task(
    session: AsyncSession, team_id: UUID, user_id: UUID, *, now: datetime
) -> m.TaskModel | None:
    """Задача, которую разумно перекинуть: ещё не начата (todo), желательно
    с ближайшим/просроченным дедлайном."""
    tasks = (
        await session.execute(
            select(m.TaskModel).where(
                m.TaskModel.team_id == team_id,
                m.TaskModel.assignee_id == user_id,
                m.TaskModel.status == "todo",
            )
        )
    ).scalars().all()
    if not tasks:
        return None
    # Сначала просроченные/с ближайшим дедлайном, потом без дедлайна.
    far_future = datetime.max.replace(tzinfo=UTC)
    tasks.sort(key=lambda t: _as_utc(t.deadline) if t.deadline else far_future)
    return tasks[0]


async def detect_interventions(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None, limit: int = 2
) -> list[Intervention]:
    """Найти проактивные интервенции для команды (перегруз/выгорание)."""
    now = now or datetime.now(UTC)
    loads = await _member_loads(session, team_id, now=now)
    if not loads:
        return []
    at_risk = sorted(
        (m_ for m_ in loads if m_.at_risk), key=lambda x: x.load_score, reverse=True
    )
    interventions: list[Intervention] = []
    used_candidates: set[UUID] = set()
    for risk in at_risk:
        if len(interventions) >= limit:
            break
        # Кандидат: самый свободный, ощутимо легче, не сам, без высокой загрузки.
        candidates = sorted(
            (
                c for c in loads
                if c.user_id != risk.user_id
                and c.user_id not in used_candidates
                and c.active_count <= max(0, risk.active_count - LOAD_GAP)
                and not c.at_risk
            ),
            key=lambda x: x.load_score,
        )
        task = await _movable_task(session, team_id, risk.user_id, now=now)
        if candidates and task is not None:
            candidate = candidates[0]
            used_candidates.add(candidate.user_id)
            reason = _risk_reason(risk)
            interventions.append(
                Intervention(
                    kind="reassign_overload",
                    at_risk=risk,
                    candidate=candidate,
                    task_id=task.id,
                    task_public_id=task.public_id,
                    task_title=task.title,
                    reason=reason,
                )
            )
        elif risk.stress >= RISK_STRESS:
            # Перебросить некуда/нечего — предложить паузу/эскалацию менеджеру.
            interventions.append(
                Intervention(
                    kind="suggest_pause",
                    at_risk=risk,
                    candidate=None,
                    task_id=None,
                    task_public_id=None,
                    task_title=None,
                    reason=_risk_reason(risk),
                )
            )
    return interventions


def _risk_reason(load: MemberLoad) -> str:
    bits = []
    if load.overdue_count >= RISK_OVERDUE:
        bits.append(f"{load.overdue_count} просрочки")
    if load.stress >= RISK_STRESS:
        bits.append("высокий стресс")
    if load.active_count:
        bits.append(f"{load.active_count} активных задач")
    return ", ".join(bits) or "перегрузка"


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
