"""Рендеринг пользовательских сообщений и inline-клавиатур (на русском).

brain-api формирует готовый текст, telegram-bot его лишь отправляет. Вся
презентация Telegram-UX сосредоточена здесь.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from brain_api.domain.entities import Task, TaskProposal
from brain_api.domain.enums import (
    PRIORITY_LABELS_RU,
    STATUS_LABELS_RU,
    TaskPriority,
    TaskStatus,
)

# Callback-data префиксы (общие с telegram-bot через данные, не код).
CB_CONFIRM = "confirm_task"
CB_REJECT = "reject_task"
CB_EDIT = "edit_task"

EDIT_STUB_TEXT = (
    "Редактирование появится в следующей версии. Сейчас отклони задачу и напиши её уточнённо."
)


def _local(dt: datetime, timezone: str) -> datetime:
    tz = ZoneInfo(timezone)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def format_deadline(dt: datetime | None, timezone: str, now: datetime | None = None) -> str:
    """Человекочитаемый дедлайн: «сегодня 18:00», «завтра 12:00» или «03.06 18:00»."""
    if dt is None:
        return "не указан"
    tz = ZoneInfo(timezone)
    local = _local(dt, timezone)
    now_local = _local(now or datetime.now(tz), timezone)
    delta_days = (local.date() - now_local.date()).days
    time_part = local.strftime("%H:%M")
    if delta_days == 0:
        return f"сегодня {time_part}"
    if delta_days == 1:
        return f"завтра {time_part}"
    if delta_days == -1:
        return f"вчера {time_part}"
    return f"{local.strftime('%d.%m')} {time_part}"


def priority_label(priority: TaskPriority) -> str:
    return PRIORITY_LABELS_RU.get(priority, priority.value)


def status_label(status: TaskStatus) -> str:
    return STATUS_LABELS_RU.get(status, status.value)


# --------------------------------------------------------------------------- #
# Proposal
# --------------------------------------------------------------------------- #
def render_proposal_text(proposal: TaskProposal, timezone: str) -> str:
    assignee = proposal.assignee_text or "не определён"
    lines = [
        "🧠 Grey Cardinal нашёл возможную задачу",
        "",
        f"Задача: {proposal.title}",
        f"Ответственный: {assignee}",
        f"Дедлайн: {format_deadline(proposal.deadline, timezone)}",
        f"Приоритет: {priority_label(proposal.priority)}",
        f"Уверенность: {proposal.confidence:.2f}",
        "",
        "Создать карточку?",
    ]
    return "\n".join(lines)


def proposal_keyboard(confirmation_id: UUID) -> dict:
    """Inline-клавиатура proposal. callback_data несёт id confirmation'а."""
    cid = str(confirmation_id)
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Создать", "callback_data": f"{CB_CONFIRM}:{cid}"},
                {"text": "❌ Отклонить", "callback_data": f"{CB_REJECT}:{cid}"},
            ],
            [
                {"text": "✏️ Изменить", "callback_data": f"{CB_EDIT}:{cid}"},
            ],
        ]
    }


# --------------------------------------------------------------------------- #
# Task created / rejected / status
# --------------------------------------------------------------------------- #
def render_task_created(task: Task, board_provider: str | None, timezone: str) -> str:
    assignee = task.assignee_text or "не определён"
    board = board_provider or "—"
    lines = [
        "✅ Задача создана",
        "",
        f"#{task.public_id} {task.title}",
        f"Ответственный: {assignee}",
        f"Дедлайн: {format_deadline(task.deadline, timezone)}",
        f"Статус: {status_label(task.status)}",
        f"Доска: {board}",
    ]
    return "\n".join(lines)


def render_task_rejected() -> str:
    return "❌ Предложение отклонено. Задача не создана."


def render_duplicate_warning(task: Task, timezone: str) -> str:
    """Сообщение «такая задача уже есть» вместо создания дубля."""
    assignee = task.assignee_text or "не определён"
    lines = [
        "Похоже, такая задача уже есть:",
        "",
        f"{task.public_id} {task.title}",
        f"Статус: {status_label(task.status)}",
        f"Ответственный: {assignee}",
        f"Дедлайн: {format_deadline(task.deadline, timezone)}",
        "",
        "Не создаю дубль.",
    ]
    return "\n".join(lines)


BOARD_SYNC_FAILED_TEXT = "Статус обновлён локально, но доску синхронизировать не удалось."


def render_status_changed(task: Task) -> str:
    mapping = {
        TaskStatus.in_progress: f"🚧 {task.public_id} взята в работу",
        TaskStatus.blocked: f"⛔ {task.public_id} заблокирована",
        TaskStatus.done: f"✅ {task.public_id} закрыта",
    }
    return mapping.get(task.status, f"Статус {task.public_id}: {status_label(task.status)}")


def render_task_list(tasks: list[Task], timezone: str) -> str:
    if not tasks:
        return "📋 Активных задач нет."
    blocks = ["📋 Активные задачи", ""]
    for task in tasks:
        assignee = task.assignee_text or "не определён"
        blocks.append(f"#{task.public_id} [{task.status.value.upper()}] {task.title}")
        blocks.append(f"Ответственный: {assignee}")
        blocks.append(f"Дедлайн: {format_deadline(task.deadline, timezone)}")
        blocks.append("")
    return "\n".join(blocks).rstrip()


# --------------------------------------------------------------------------- #
# Reminders / digest
# --------------------------------------------------------------------------- #
def render_deadline_reminder(task: Task, timezone: str) -> str:
    assignee = task.assignee_text or "не определён"
    return "\n".join(
        [
            "⏰ Скоро дедлайн",
            "",
            f"{task.public_id} {task.title}",
            f"Дедлайн: {format_deadline(task.deadline, timezone)}",
            f"Ответственный: {assignee}",
        ]
    )


def render_stale_reminder(task: Task) -> str:
    return "\n".join(
        [
            "👀 Нужен статус",
            "",
            f"{task.public_id} {task.title} давно без обновлений.",
            "Выбери статус кнопкой ниже 👇",
        ]
    )


def render_digest(
    active: list[Task],
    closed_today: int,
    overdue: int,
    timezone: str,
) -> str:
    lines = ["🌙 Вечерний дайджест Grey Cardinal", "", "Активные задачи:"]
    if active:
        for i, task in enumerate(active, start=1):
            lines.append(
                f"{i}. #{task.public_id} {task.title} — "
                f"дедлайн {format_deadline(task.deadline, timezone)}"
            )
    else:
        lines.append("— нет активных задач")
    lines.append("")
    lines.append(f"Закрыто сегодня: {closed_today}")
    lines.append(f"Просрочено: {overdue}")
    return "\n".join(lines)


def render_personal_digest(
    name: str,
    active: list[Task],
    overdue: list[Task],
    completed_today: list[Task],
    stale: list[Task],
    timezone: str,
) -> str:
    """Персональный вечерний дайджест одного пользователя."""
    lines = ["🌙 Вечерний дайджест Grey Cardinal", ""]
    lines.append(f"{name}, твои задачи:")
    lines.append("")

    lines.append("Активные:")
    if active:
        for i, task in enumerate(active, start=1):
            if task.deadline is not None:
                tail = f"дедлайн {format_deadline(task.deadline, timezone)}"
            else:
                tail = "без дедлайна"
            lines.append(f"{i}. {task.public_id} {task.title} — {tail}")
    else:
        lines.append("— нет активных задач")

    if overdue:
        lines.append("")
        lines.append("Просрочено:")
        for task in overdue:
            lines.append(f"• {task.public_id} {task.title}")

    if stale:
        lines.append("")
        lines.append("Давно без обновлений:")
        for task in stale:
            lines.append(f"• {task.public_id} {task.title}")

    lines.append("")
    lines.append(f"Закрыто сегодня: {len(completed_today)}")
    return "\n".join(lines)
