"""Адресная доставка и анти-спам политика напоминаний.

* `resolve_recipient` — кому и куда слать: в личку исполнителю (если есть
  telegram_user_id) или в рабочий чат с упоминанием.
* `check_anti_spam` — quiet hours / лимит в день / минимальный интервал на
  одного пользователя. Возвращает причину подавления или None.

Причины подавления (значения для websocket-события `reminder_suppressed`):
`quiet_hours | max_daily | min_interval | already_sent`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from brain_api.application.config import AppConfig
from brain_api.application.ports import UnitOfWork
from brain_api.domain.entities import Task


@dataclass(slots=True)
class ReminderRecipient:
    """Куда доставить напоминание."""

    chat_id: int
    user_id: int | None  # telegram_user_id, если личка (для анти-спама)
    is_private: bool
    mention: str | None  # имя для упоминания в групповом fallback


def parse_hhmm(value: str) -> time:
    """'22:00' -> time(22, 0). При ошибке — полночь."""
    try:
        hh, _, mm = value.partition(":")
        return time(int(hh), int(mm or 0))
    except (ValueError, TypeError):
        return time(0, 0)


def in_quiet_hours(now: datetime, start: time, end: time) -> bool:
    """Попадает ли момент в «тихие часы».

    Окно может пересекать полночь (например, 22:00..09:00).
    """
    current = now.timetz().replace(tzinfo=None)
    if start == end:
        return False
    if start < end:
        return start <= current < end
    # Ночное окно через полночь.
    return current >= start or current < end


async def resolve_recipient(
    uow: UnitOfWork, task: Task, default_chat_id: int | None
) -> ReminderRecipient | None:
    """Определить получателя напоминания по задаче.

    1. Исполнитель известен и у него есть telegram_user_id -> личка.
    2. Иначе -> рабочий чат с упоминанием имени.
    3. Нет рабочего чата -> None (отправлять некуда).
    """
    user = await uow.users.get(task.assignee_id) if task.assignee_id else None
    if user is not None and user.telegram_user_id is not None:
        return ReminderRecipient(
            chat_id=user.telegram_user_id,
            user_id=user.telegram_user_id,
            is_private=True,
            mention=user.display_name,
        )
    if default_chat_id is None:
        return None
    mention = task.assignee_text or (user.display_name if user else None)
    return ReminderRecipient(
        chat_id=default_chat_id, user_id=None, is_private=False, mention=mention
    )


async def check_anti_spam(
    uow: UnitOfWork,
    config: AppConfig,
    now: datetime,
    recipient: ReminderRecipient,
) -> str | None:
    """Проверить анти-спам ограничения. Вернуть причину подавления или None."""
    quiet_start = parse_hhmm(config.reminder_quiet_hours_start)
    quiet_end = parse_hhmm(config.reminder_quiet_hours_end)
    if in_quiet_hours(now, quiet_start, quiet_end):
        return "quiet_hours"

    # Лимиты считаем только для персональных получателей (по telegram_user_id).
    if recipient.user_id is not None:
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = await uow.reminders.count_for_user_since(recipient.user_id, start_of_day)
        if sent_today >= config.reminder_max_daily_per_user:
            return "max_daily"

        last = await uow.reminders.last_sent_to_user(recipient.user_id)
        if last is not None:
            if last.tzinfo is None and now.tzinfo is not None:
                last = last.replace(tzinfo=now.tzinfo)
            if now - last < timedelta(minutes=config.reminder_min_interval_minutes):
                return "min_interval"

    return None
