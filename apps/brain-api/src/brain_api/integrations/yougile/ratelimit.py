"""Process-local token bucket for YouGile's 50 req/min-per-key limit.

One bucket per API key, shared across YouGileClient instances (the board adapter
is recreated/cached per team, but the bucket must persist so the limit is real).
Time/sleep are injectable for deterministic tests.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

TimeFn = Callable[[], float]
SleepFn = Callable[[float], Awaitable[None]]


class TokenBucket:
    def __init__(
        self,
        rate_per_minute: int,
        *,
        capacity: int | None = None,
        time_fn: TimeFn = time.monotonic,
        sleep_fn: SleepFn = asyncio.sleep,
    ) -> None:
        self.capacity = float(capacity if capacity is not None else rate_per_minute)
        self.rate = rate_per_minute / 60.0  # tokens per second
        self._tokens = self.capacity
        self._time = time_fn
        self._sleep = sleep_fn
        self._updated = time_fn()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._time()
        self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
        self._updated = now

    async def acquire(self) -> None:
        # Hold the lock for the whole operation so concurrent callers queue and
        # the limit is enforced in arrival order.
        async with self._lock:
            self._refill()
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self.rate
                await self._sleep(wait)
                self._refill()
            self._tokens -= 1.0

    def remaining(self) -> int:
        self._refill()
        return int(self._tokens)


_buckets: dict[str, TokenBucket] = {}


def bucket_for(api_key: str, rate_per_minute: int = 50) -> TokenBucket:
    """Return the shared bucket for this key, creating it on first use."""
    bucket = _buckets.get(api_key)
    if bucket is None:
        bucket = TokenBucket(rate_per_minute)
        _buckets[api_key] = bucket
    return bucket
