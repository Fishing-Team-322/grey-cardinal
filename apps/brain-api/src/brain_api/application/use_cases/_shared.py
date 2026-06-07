"""Общие помощники use case'ов (создание proposal/confirmation из извлечённой задачи)."""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import BoardGateway, EventPublisher, UnitOfWork
from brain_api.application.rendering import proposal_keyboard, render_proposal_text
from brain_api.application.use_cases.gamification import GamificationService
from brain_api.domain.entities import AuditLog, BoardCard, Confirmation, Task, TaskProposal, User
from brain_api.domain.enums import (
    BoardProvider,
    ConfirmationStatus,
    TaskPriority,
    TaskSource,
    TaskStatus,
    XpEventKind,
)
from brain_api.domain.services import format_public_id
from grey_cardinal_contracts import (
    EventName,
    SendMessageAction,
    TaskExtractionResult,
    WebsocketEvent,
)

logger = logging.getLogger(__name__)

_PROVIDER_LABEL = {
    BoardProvider.mock: "Mock",
    BoardProvider.yougile: "YouGile",
    BoardProvider.jira: "Jira",
}


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
    proposal, confirmation = await create_proposal_and_confirmation(
        uow,
        events,
        source=source,
        raw_text=raw_text,
        extraction=extraction,
        chat_telegram_id=chat_telegram_id,
        source_message_id=source_message_id,
        source_transcript_id=source_transcript_id,
    )

    text = render_proposal_text(proposal, config.timezone)
    return SendMessageAction(
        chat_id=chat_telegram_id or 0,
        text=text,
        reply_markup=proposal_keyboard(confirmation.id),
    )


async def create_proposal_and_confirmation(
    uow: UnitOfWork,
    events: EventPublisher,
    *,
    source: TaskSource,
    raw_text: str,
    extraction: TaskExtractionResult,
    chat_telegram_id: int | None,
    source_message_id: UUID | None = None,
    source_transcript_id: UUID | None = None,
) -> tuple[TaskProposal, Confirmation]:
    """Создать proposal + pending confirmation и опубликовать событие proposal."""
    known = await uow.users.list_known()
    assignee_text, assignee_id = _match_assignee(extraction.assignee, known)

    proposal = TaskProposal(
        id=uuid4(),
        team_id=getattr(extraction, "team_id", None),
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
        team_id=proposal.team_id,
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

    return proposal, confirmation


async def create_task_from_proposal(
    uow: UnitOfWork,
    board: BoardGateway,
    events: EventPublisher,
    config: AppConfig,
    proposal: TaskProposal,
    *,
    confirmation: Confirmation | None = None,
    actor_telegram_id: int | None = None,
    telegram_chat_id: int | None = None,
    telegram_message_id: int | None = None,
) -> tuple[Task, str | None]:
    """Создать task + board card из proposal. Используется confirm и auto-create путём."""
    project = await uow.projects.ensure_default(config.default_workspace_name)
    sequence = await uow.tasks.next_sequence(proposal.team_id)
    now = config.now()
    task = Task(
        id=uuid4(),
        team_id=proposal.team_id,
        public_id=format_public_id(sequence),
        title=proposal.title,
        description=proposal.description,
        status=TaskStatus.todo,
        priority=proposal.priority,
        source=proposal.source,
        project_id=project.id,
        assignee_id=proposal.assignee_id,
        assignee_text=proposal.assignee_text,
        deadline=proposal.deadline,
        source_message_id=proposal.source_message_id,
        created_from_proposal_id=proposal.id,
        last_status_update_at=now,
    )
    await uow.tasks.add(task)

    provider_label = await create_board_card(uow, board, task)

    if confirmation is not None:
        confirmation.status = ConfirmationStatus.accepted
        confirmation.created_task_id = task.id
        confirmation.telegram_chat_id = telegram_chat_id
        confirmation.telegram_message_id = telegram_message_id
        await uow.confirmations.update(confirmation)

    await uow.audit.add(
        AuditLog(
            id=uuid4(),
            actor_type="user" if actor_telegram_id else "system",
            actor_id=str(actor_telegram_id) if actor_telegram_id else None,
            action="task_created",
            entity_type="task",
            entity_id=task.id,
            payload={"public_id": task.public_id, "board": provider_label},
        )
    )

    await events.publish(
        WebsocketEvent(
            event=EventName.task_created,
            payload={
                "task_id": str(task.id),
                "public_id": task.public_id,
                "title": task.title,
                "status": task.status.value,
                "assignee": task.assignee_text,
                "board": provider_label,
            },
        )
    )

    if task.assignee_id is not None:
        await GamificationService().grant(
            uow,
            user_id=task.assignee_id,
            workspace_id=task.project_id,
            task_id=task.id,
            kind=XpEventKind.task_confirmed,
            reason=f"Подтвердили задачу {task.public_id}",
            idempotency_key=f"task_confirmed:{task.id}",
        )

    return task, provider_label


async def create_board_card(
    uow: UnitOfWork,
    board: BoardGateway,
    task: Task,
) -> str | None:
    """Создать карточку на доске. Ошибка доски не теряет локальную задачу."""
    try:
        result = await board.create_card(task)
    except Exception as exc:
        logger.warning("Board card creation failed for %s: %s", task.public_id, exc)
        await uow.audit.add(
            AuditLog(
                id=uuid4(),
                actor_type="system",
                action="board_card_failed",
                entity_type="task",
                entity_id=task.id,
                payload={"error": str(exc)},
            )
        )
        return "недоступна, задача сохранена локально"

    provider = BoardProvider(result.provider.value)
    await uow.board_cards.add(
        BoardCard(
            id=uuid4(),
            team_id=task.team_id,
            task_id=task.id,
            provider=provider,
            external_card_id=result.external_card_id,
            external_url=result.external_url,
            external_payload=result.external_payload,
        )
    )
    return _PROVIDER_LABEL.get(provider, provider.value)
