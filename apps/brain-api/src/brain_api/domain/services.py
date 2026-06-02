"""Доменные сервисы — чистая бизнес-логика без I/O."""

from __future__ import annotations

from datetime import datetime, timedelta

from brain_api.domain.entities import Task
from brain_api.domain.enums import TaskStatus

PUBLIC_ID_PREFIX = "GC"


def format_public_id(sequence: int) -> str:
    """`12` -> `GC-12`. Префикс фиксирован для P0."""
    return f"{PUBLIC_ID_PREFIX}-{sequence}"


def parse_public_id(value: str) -> int | None:
    """`GC-12`/`gc-12`/`#GC-12`/`12` -> 12, иначе None."""
    cleaned = value.strip().lstrip("#").upper()
    if cleaned.startswith(f"{PUBLIC_ID_PREFIX}-"):
        cleaned = cleaned[len(PUBLIC_ID_PREFIX) + 1 :]
    if cleaned.isdigit():
        return int(cleaned)
    return None


# Разрешённые переходы статусов команд бота на P0.
_COMMAND_TRANSITIONS: dict[str, TaskStatus] = {
    "start_task": TaskStatus.in_progress,
    "block": TaskStatus.blocked,
    "done": TaskStatus.done,
}


def status_for_command(command: str) -> TaskStatus | None:
    return _COMMAND_TRANSITIONS.get(command)


def is_deadline_reminder_due(task: Task, now: datetime, hours_before: int) -> bool:
    """Подходит ли задача под напоминание о дедлайне."""
    if task.deadline is None:
        return False
    if task.status.is_terminal:
        return False
    return task.deadline <= now + timedelta(hours=hours_before)


def is_stale(task: Task, now: datetime, stale_hours: int) -> bool:
    """Задача «зависла»: активна и давно не обновлялась."""
    if not task.status.is_active:
        return False
    reference = task.last_status_update_at or task.updated_at or task.created_at
    if reference is None:
        return False
    return reference <= now - timedelta(hours=stale_hours)
