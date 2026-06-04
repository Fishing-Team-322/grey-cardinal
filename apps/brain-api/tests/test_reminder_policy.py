"""Юнит-тесты анти-спам политики напоминаний (quiet hours / лимиты / интервал)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from brain_api.application.config import AppConfig
from brain_api.application.reminder_policy import (
    ReminderRecipient,
    check_anti_spam,
    in_quiet_hours,
    parse_hhmm,
)

TZ = ZoneInfo("Europe/Moscow")


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 2, hour, minute, tzinfo=TZ)


class _FakeReminders:
    def __init__(self, count: int = 0, last: datetime | None = None) -> None:
        self._count = count
        self._last = last

    async def count_for_user_since(self, user_id: int, since: datetime) -> int:
        return self._count

    async def last_sent_to_user(self, user_id: int) -> datetime | None:
        return self._last


class _FakeUow:
    def __init__(self, reminders: _FakeReminders) -> None:
        self.reminders = reminders


def _private(user_id: int = 555) -> ReminderRecipient:
    return ReminderRecipient(chat_id=user_id, user_id=user_id, is_private=True, mention="Петя")


def _group() -> ReminderRecipient:
    return ReminderRecipient(chat_id=-100, user_id=None, is_private=False, mention="Петя")


def test_parse_hhmm():
    assert parse_hhmm("22:00") == time(22, 0)
    assert parse_hhmm("09:30") == time(9, 30)
    assert parse_hhmm("bad") == time(0, 0)


def test_in_quiet_hours_overnight_window():
    start, end = time(22, 0), time(9, 0)
    assert in_quiet_hours(_at(23), start, end) is True
    assert in_quiet_hours(_at(2), start, end) is True
    assert in_quiet_hours(_at(8, 59), start, end) is True
    assert in_quiet_hours(_at(9, 0), start, end) is False
    assert in_quiet_hours(_at(15), start, end) is False


def test_in_quiet_hours_same_day_window():
    start, end = time(13, 0), time(14, 0)
    assert in_quiet_hours(_at(13, 30), start, end) is True
    assert in_quiet_hours(_at(15), start, end) is False


async def test_quiet_hours_suppresses():
    config = AppConfig(reminder_quiet_hours_start="22:00", reminder_quiet_hours_end="09:00")
    uow = _FakeUow(_FakeReminders())
    reason = await check_anti_spam(uow, config, _at(23, 30), _private())
    assert reason == "quiet_hours"


async def test_max_daily_suppresses():
    config = AppConfig(
        reminder_max_daily_per_user=3,
        reminder_quiet_hours_start="22:00",
        reminder_quiet_hours_end="09:00",
    )
    uow = _FakeUow(_FakeReminders(count=3))
    reason = await check_anti_spam(uow, config, _at(15), _private())
    assert reason == "max_daily"


async def test_min_interval_suppresses():
    config = AppConfig(
        reminder_min_interval_minutes=120,
        reminder_max_daily_per_user=10,
        reminder_quiet_hours_start="22:00",
        reminder_quiet_hours_end="09:00",
    )
    last = _at(15, 0) - timedelta(minutes=30)
    uow = _FakeUow(_FakeReminders(count=1, last=last))
    reason = await check_anti_spam(uow, config, _at(15), _private())
    assert reason == "min_interval"


async def test_allowed_when_within_limits():
    config = AppConfig(
        reminder_min_interval_minutes=120,
        reminder_max_daily_per_user=3,
        reminder_quiet_hours_start="22:00",
        reminder_quiet_hours_end="09:00",
    )
    last = _at(15, 0) - timedelta(hours=5)
    uow = _FakeUow(_FakeReminders(count=1, last=last))
    reason = await check_anti_spam(uow, config, _at(15), _private())
    assert reason is None


async def test_group_recipient_only_checks_quiet_hours():
    config = AppConfig(
        reminder_max_daily_per_user=0,
        reminder_quiet_hours_start="22:00",
        reminder_quiet_hours_end="09:00",
    )
    uow = _FakeUow(_FakeReminders(count=99))
    # user_id None -> лимиты на пользователя не применяются, только quiet hours.
    reason = await check_anti_spam(uow, config, _at(15), _group())
    assert reason is None
