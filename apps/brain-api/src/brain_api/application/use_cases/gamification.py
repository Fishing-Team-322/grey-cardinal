from __future__ import annotations

from uuid import UUID, uuid4

from brain_api.application.ports import UnitOfWork
from brain_api.domain.entities import UserXpEvent
from brain_api.domain.enums import XpEventKind


class GamificationService:
    POINTS: dict[XpEventKind, int] = {
        XpEventKind.task_created_from_speech: 5,
        XpEventKind.task_confirmed: 10,
        XpEventKind.task_completed: 20,
        XpEventKind.status_updated: 3,
        XpEventKind.meeting_joined: 2,
        XpEventKind.meeting_summary_ready: 5,
        XpEventKind.streak_bonus: 10,
        XpEventKind.risk_resolved: 10,
    }

    async def grant(
        self,
        uow: UnitOfWork,
        *,
        user_id: UUID,
        kind: XpEventKind,
        reason: str,
        workspace_id: UUID | None = None,
        task_id: UUID | None = None,
        meeting_id: UUID | None = None,
        idempotency_key: str,
    ) -> UserXpEvent | None:
        metadata = {"idempotency_key": idempotency_key}
        return await uow.gamification.add_event_once(
            UserXpEvent(
                id=uuid4(),
                user_id=user_id,
                workspace_id=workspace_id,
                task_id=task_id,
                meeting_id=meeting_id,
                kind=kind,
                points=self.POINTS[kind],
                reason=reason,
                metadata=metadata,
            )
        )
