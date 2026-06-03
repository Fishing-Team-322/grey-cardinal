"""Общие помощники use case'ов (создание proposal/confirmation из извлечённой задачи)."""

from __future__ import annotations

from uuid import UUID, uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import EventPublisher, UnitOfWork
from brain_api.application.rendering import proposal_keyboard, render_proposal_text
from brain_api.domain.entities import Confirmation, TaskProposal, User
from brain_api.domain.enums import ConfirmationStatus, TaskPriority, TaskSource
from grey_cardinal_contracts import (
    EventName,
    SendMessageAction,
    TaskExtractionResult,
    WebsocketEvent,
)


def match_assignee(assignee: str | None, known: list[User]) -> tuple[str | None, UUID | None]:
    """Сопоставить текст ответственного с известным пользователем.

    Возвращает (отображаемый текст, id пользователя | None).
    """
    if not assignee:
        return None, None
    needle = assignee.strip().lstrip("@").lower()
    for user in known:
        if user.telegram_username and user.telegram_username.lower() == needle:
            return assignee, user.id
        if user.display_name and user.display_name.lower() == needle:
            return assignee, user.id
        # частичное совпадение по имени (Петя -> Пётр Петров)
        if user.display_name and needle and needle in user.display_name.lower():
            return assignee, user.id
    return assignee, None


# Обратная совместимость для внутренних вызовов.
_match_assignee = match_assignee


async def create_proposal_with_confirmation(
    uow: UnitOfWork,
    events: EventPublisher,
    config: AppConfig,
    *,
    source: TaskSource,
    raw_text: str,
    extraction: TaskExtractionResult,
    chat_telegram_id: int | None,
    source_message_id: UUID | None = None,
    source_transcript_id: UUID | None = None,
) -> SendMessageAction:
    """Создать proposal + confirmation, опубликовать событие, вернуть action для бота."""
    known = await uow.users.list_known()
    assignee_text, assignee_id = _match_assignee(extraction.assignee, known)

    proposal = TaskProposal(
        id=uuid4(),
        source=source,
        title=extraction.title or raw_text[:120],
        description=extraction.description,
        assignee_text=assignee_text,
        assignee_id=assignee_id,
        deadline=extraction.deadline,
        priority=TaskPriority(extraction.priority.value),
        confidence=extraction.confidence,
        raw_text=raw_text,
        extractor_payload=extraction.model_dump(mode="json"),
        source_message_id=source_message_id,
        source_transcript_id=source_transcript_id,
    )
    await uow.proposals.add(proposal)

    confirmation = Confirmation(
        id=uuid4(),
        proposal_id=proposal.id,
        status=ConfirmationStatus.pending,
        telegram_chat_id=chat_telegram_id,
    )
    await uow.confirmations.add(confirmation)

    await events.publish(
        WebsocketEvent(
            event=EventName.task_proposed,
            payload={
                "proposal_id": str(proposal.id),
                "confirmation_id": str(confirmation.id),
                "title": proposal.title,
                "assignee": proposal.assignee_text,
                "priority": proposal.priority.value,
                "confidence": proposal.confidence,
                "source": source.value,
            },
        )
    )

    text = render_proposal_text(proposal, config.timezone)
    return SendMessageAction(
        chat_id=chat_telegram_id or 0,
        text=text,
        reply_markup=proposal_keyboard(confirmation.id),
    )
