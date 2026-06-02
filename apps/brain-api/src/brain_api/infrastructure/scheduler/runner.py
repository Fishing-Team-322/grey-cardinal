"""Простой async-планировщик на asyncio (без внешних зависимостей).

Поддерживает периодические задачи (every) и ежедневный запуск в заданный час
(daily_at). Каждая задача — это async-callable без аргументов; ошибки внутри
логируются и не убивают цикл.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

JobFn = Callable[[], Awaitable[None]]


class AsyncScheduler:
    def __init__(self, timezone: str = "Europe/Moscow") -> None:
        self._tz = ZoneInfo(timezone)
        self._tasks: list[asyncio.Task] = []
        self._stopping = asyncio.Event()

    def every(self, seconds: float, job: JobFn, name: str) -> None:
        self._tasks.append(asyncio.create_task(self._run_every(seconds, job, name), name=name))

    def daily_at(self, hour: int, job: JobFn, name: str) -> None:
        self._tasks.append(asyncio.create_task(self._run_daily(hour, job, name), name=name))

    async def _run_every(self, seconds: float, job: JobFn, name: str) -> None:
        # Небольшая стартовая задержка, чтобы дать API подняться.
        await self._sleep(5)
        while not self._stopping.is_set():
            await self._safe_run(job, name)
            await self._sleep(seconds)

    async def _run_daily(self, hour: int, job: JobFn, name: str) -> None:
        while not self._stopping.is_set():
            delay = self._seconds_until_hour(hour)
            await self._sleep(delay)
            if self._stopping.is_set():
                break
            await self._safe_run(job, name)
            await self._sleep(60)  # защита от двойного запуска в тот же час

    def _seconds_until_hour(self, hour: int) -> float:
        now = datetime.now(self._tz)
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return (target - now).total_seconds()

    async def _safe_run(self, job: JobFn, name: str) -> None:
        try:
            await job()
        except Exception:
            logger.exception("Scheduler job '%s' failed", name)

    async def _sleep(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)

    async def stop(self) -> None:
        self._stopping.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()
