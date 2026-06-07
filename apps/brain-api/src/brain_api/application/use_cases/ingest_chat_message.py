"""Use case: приём нормализованного Telegram-сообщения из чата.

Поток: сохранить сообщение -> извлечь задачу -> policy-фильтр -> детекция дубля
-> proposal с подтверждением. Болтовня и низкоуверенные срабатывания не доходят
до чата; дубли отвечают «такая задача уже есть» и не создают вторую карточку.
"""

from __future__ import annotations

import re
from uuid import uuid4

from brain_api.application.config import AppConfig
from brain_api.application.ports import BoardGateway, EventPublisher, TaskExtractor, UnitOfWork
from brain_api.application.rendering import BOARD_SYNC_FAILED_TEXT, render_duplicate_warning
from brain_api.application.text_policy import evaluate_task_extraction
from brain_api.application.use_cases._shared import (
    create_proposal_and_confirmation,
    create_proposal_with_confirmation,
    create_task_from_proposal,
    match_assignee,
)
from brain_api.application.use_cases.find_similar_task import FindSimilarTask
from brain_api.domain.entities import AuditLog, ChatMessage
from brain_api.domain.enums import TaskSource, TaskStatus
from brain_api.domain.services import format_public_id, parse_public_id
from grey_cardinal_contracts import (
    ActionsResponse,
    EventName,
    KnownUser,
    SendMessageAction,
    TelegramMessageEvent,
    WebsocketEvent,
)


class IngestChatMessage:
    def __init__(
        self,
        uow: UnitOfWork,
        extractor: TaskExtractor,
        events: EventPublisher,
        config: AppConfig,
        board: BoardGateway | None = None,
    ) -> None:
        self._uow = uow
        self._extractor = extractor
        self._events = events
        self._config = config
        self._board = board

    async def execute(self, event: TelegramMessageEvent) -> ActionsResponse:
        uow = self._uow

        project = await uow.projects.ensure_default(self._config.default_workspace_name)
        chat = await uow.chats.upsert(
            telegram_chat_id=event.chat.id,
            chat_type=event.chat.type,
            title=event.chat.title,
            project_id=project.id,
        )
        sender = await uow.users.upsert_from_telegram(
            telegram_user_id=event.sender.id,
            username=event.sender.username,
            display_name=_display_name(event),
        )

        # Идемпотентность: одно Telegram-сообщение не должно обрабатываться дважды.
        existing = await uow.messages.get_by_tg(chat.id, event.message_id)
        if existing is not None:
            await uow.commit()
            return ActionsResponse(actions=[])

        message = ChatMessage(
            id=uuid4(),
            telegram_message_id=event.message_id,
            chat_id=chat.id,
            sender_id=sender.id,
            text=event.text,
            raw_json=event.raw or {},
            message_thread_id=event.message_thread_id,
        )
        message = await uow.messages.add(message)

        if await self._try_mark_assigned_task_in_progress(event, sender):
            await uow.commit()
            return ActionsResponse(actions=[])

        conversation_context = await self._conversation_context(chat.id, message.id)

        known_users = [
            KnownUser(display_name=u.display_name, telegram_username=u.telegram_username)
            for u in await uow.users.list_known()
        ]
        extraction = await self._extractor.extract_task(
            text=event.text,
            now=self._config.now(),
            timezone=self._config.timezone,
            known_users=known_users,
            conversation_context=conversation_context,
        )

        # Policy-слой: отсекаем болтовню и низкоуверенные срабатывания до чата.
        decision = evaluate_task_extraction(extraction, event.text, self._config)
        if not decision.create_proposal:
            if extraction.has_task:
                # Был сигнал, но policy не пропустил — оставляем audit-след, в чат молчим.
                await uow.audit.add(
                    AuditLog(
                        id=uuid4(),
                        actor_type="system",
                        action="task_extraction_suppressed",
                        entity_type="chat_message",
                        entity_id=message.id,
                        payload={
                            "reason": decision.reason,
                            "confidence": extraction.confidence,
                            "title": extraction.title,
                        },
                    )
                )
            await uow.commit()
            return ActionsResponse(actions=[])

        # Детекция дубля: сопоставляем исполнителя и ищем похожую активную задачу.
        known = await uow.users.list_known()
        assignee_text, assignee_id = match_assignee(extraction.assignee, known)
        new_title = extraction.title or event.text[:120]
        similar = await FindSimilarTask(uow, self._config).execute(
            title=new_title,
            assignee_id=assignee_id,
            assignee_text=assignee_text,
            deadline=extraction.deadline,
            project_id=project.id,
        )
        if similar.is_duplicate and similar.task is not None:
            await self._events.publish(
                WebsocketEvent(
                    event=EventName.duplicate_task_detected,
                    payload={
                        "existing_task_id": str(similar.task.id),
                        "public_id": similar.task.public_id,
                        "new_title": new_title,
                        "score": similar.score,
                    },
                )
            )
            await uow.audit.add(
                AuditLog(
                    id=uuid4(),
                    actor_type="system",
                    action="duplicate_task_detected",
                    entity_type="task",
                    entity_id=similar.task.id,
                    payload={
                        "public_id": similar.task.public_id,
                        "new_title": new_title,
                        "score": similar.score,
                    },
                )
            )
            await uow.commit()
            text = render_duplicate_warning(similar.task, self._config.timezone)
            return ActionsResponse(actions=[SendMessageAction(chat_id=event.chat.id, text=text)])

        if not chat.task_confirmation_required and self._board is not None:
            proposal, confirmation = await create_proposal_and_confirmation(
                uow,
                self._events,
                source=TaskSource.telegram_chat,
                raw_text=_raw_task_text(event.text, conversation_context),
                extraction=extraction,
                chat_telegram_id=event.chat.id,
                source_message_id=message.id,
            )
            await create_task_from_proposal(
                uow,
                self._board,
                self._events,
                self._config,
                proposal,
                confirmation=confirmation,
                telegram_chat_id=event.chat.id,
            )
            await uow.commit()
            return ActionsResponse(actions=[])

        action = await create_proposal_with_confirmation(
            uow,
            self._events,
            self._config,
            source=TaskSource.telegram_chat,
            raw_text=_raw_task_text(event.text, conversation_context),
            extraction=extraction,
            chat_telegram_id=event.chat.id,
            source_message_id=message.id,
        )
        await uow.commit()
        return ActionsResponse(actions=[action])

    async def _try_mark_assigned_task_in_progress(
        self, event: TelegramMessageEvent, sender
    ) -> bool:
        if self._board is None or not _looks_like_self_start(event.text):
            return False

        task = await self._resolve_self_start_task(event.text, sender.id)
        if task is None or task.status != TaskStatus.todo:
            return False

        now = self._config.now()
        task.status = TaskStatus.in_progress
        task.last_status_update_at = now
        await self._uow.tasks.update(task)

        board_synced = await self._sync_board_in_progress(task)
        await self._uow.audit.add(
            AuditLog(
                id=uuid4(),
                actor_type="user",
                actor_id=str(event.sender.id),
                action="task_status_changed_by_chat_signal",
                entity_type="task",
                entity_id=task.id,
                payload={
                    "public_id": task.public_id,
                    "status": task.status.value,
                    "board_synced": board_synced,
                    "text": event.text,
                },
            )
        )
        await self._events.publish(
            WebsocketEvent(
                event=EventName.task_status_changed,
                payload={
                    "task_id": str(task.id),
                    "public_id": task.public_id,
                    "status": task.status.value,
                    "source": "telegram_chat_signal",
                },
            )
        )
        return True

    async def _conversation_context(self, chat_id, current_message_id) -> str | None:
        recent = await self._uow.messages.list_recent_for_chat(chat_id, limit=8)
        prior = [item for item in recent if item.id != current_message_id]
        lines = [item.text.strip() for item in prior if item.text.strip()]
        if not lines:
            return None
        return "\n".join(lines[-7:])

    async def _resolve_self_start_task(self, text: str, sender_id):
        explicit = _public_id_from_text(text)
        if explicit is not None:
            return await self._uow.tasks.get_by_public_id(explicit)

        tasks = await self._uow.tasks.list_for_user(sender_id)
        candidates = [
            task
            for task in tasks
            if task.assignee_id == sender_id and task.status == TaskStatus.todo
        ]
        if len(candidates) == 1:
            return candidates[0]
        return None

    async def _sync_board_in_progress(self, task) -> bool:
        card = await self._uow.board_cards.get_by_task(task.id)
        if card is None:
            return True
        if self._board is None:
            return False
        try:
            await self._board.move_card(card.external_card_id, TaskStatus.in_progress)
        except Exception as exc:
            await self._uow.audit.add(
                AuditLog(
                    id=uuid4(),
                    actor_type="system",
                    action="board_sync_failed",
                    entity_type="task",
                    entity_id=task.id,
                    payload={
                        "error": str(exc),
                        "status": TaskStatus.in_progress.value,
                        "text": BOARD_SYNC_FAILED_TEXT,
                    },
                )
            )
            return False
        return True


def _display_name(event: TelegramMessageEvent) -> str:
    s = event.sender
    parts = [p for p in (s.first_name, s.last_name) if p]
    if parts:
        return " ".join(parts)
    return s.username or f"user{s.id}"


_SELF_START_PATTERNS = (
    "начал делать",
    "начала делать",
    "начинаю делать",
    "уже делаю",
    "делаю",
    "беру в работу",
    "взял в работу",
    "взяла в работу",
    "приступил",
    "приступила",
)


def _looks_like_self_start(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in _SELF_START_PATTERNS)


def _public_id_from_text(text: str) -> str | None:
    match = re.search(r"(?:#)?GC-\d+", text, flags=re.IGNORECASE)
    if match is None:
        return None
    sequence = parse_public_id(match.group(0))
    return format_public_id(sequence) if sequence is not None else None


def _raw_task_text(text: str, conversation_context: str | None) -> str:
    if not conversation_context:
        return text
    return f"{conversation_context}\n{text}"
