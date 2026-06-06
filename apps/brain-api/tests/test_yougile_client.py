"""YouGileClient: success, pagination, 429 retry, error mapping, rate limit.

All HTTP is mocked via httpx.MockTransport — no network. Sleeps are stubbed so
retry/backoff tests are instant.
"""

from __future__ import annotations

import httpx
import pytest

from brain_api.integrations.yougile.client import YouGileClient
from brain_api.integrations.yougile.exceptions import (
    YouGileAuthError,
    YouGileNotFound,
    YouGilePermissionError,
    YouGileServerError,
)
from brain_api.integrations.yougile.ratelimit import TokenBucket


def _client(handler, **kw) -> YouGileClient:
    recorded: list[float] = []

    async def _sleep(s: float) -> None:
        recorded.append(s)

    # Unlimited bucket so rate limiting doesn't interfere with HTTP tests.
    c = YouGileClient(
        "test-key",
        transport=httpx.MockTransport(handler),
        bucket=TokenBucket(10_000_000),
        sleep_fn=_sleep,
        backoff_base=0.01,
        **kw,
    )
    c._recorded_sleeps = recorded  # type: ignore[attr-defined]
    return c


def _page(content, has_next=False):
    return {"paging": {"count": len(content), "limit": 50, "offset": 0, "next": has_next}, "content": content}


@pytest.mark.asyncio
async def test_list_projects_success_and_bearer_header():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("Authorization")
        return httpx.Response(200, json=_page([{"id": "p1", "title": "Proj"}]))

    projects = await _client(handler).list_projects()
    assert projects == [{"id": "p1", "title": "Proj"}]
    assert seen["auth"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_pagination_merges_pages():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=_page([{"id": "a"}], has_next=True))
        return httpx.Response(200, json=_page([{"id": "b"}], has_next=False))

    tasks = await _client(handler).list_tasks(column_id="c1")
    assert [t["id"] for t in tasks] == ["a", "b"]
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_auth_endpoints_send_no_bearer():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("Authorization")
        return httpx.Response(200, json={"content": [{"id": "co", "name": "C"}]})

    companies = await _client(handler).auth_companies("a@b.com", "pw")
    assert companies == [{"id": "co", "name": "C"}]
    assert seen["auth"] is None


@pytest.mark.asyncio
async def test_429_is_retried_after_retry_after_then_succeeds():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={})
        return httpx.Response(200, json=_page([{"id": "p1"}]))

    c = _client(handler)
    projects = await c.list_projects()
    assert projects == [{"id": "p1"}]
    assert calls["n"] == 2
    assert 2.0 in c._recorded_sleeps  # respected Retry-After


@pytest.mark.asyncio
async def test_401_raises_auth_error_without_retry():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="bad key")

    with pytest.raises(YouGileAuthError):
        await _client(handler).list_projects()
    assert calls["n"] == 1  # 4xx not retried


@pytest.mark.asyncio
async def test_403_and_404_mapping():
    with pytest.raises(YouGilePermissionError):
        await _client(lambda r: httpx.Response(403)).list_projects()
    with pytest.raises(YouGileNotFound):
        await _client(lambda r: httpx.Response(404)).get_task("x")


@pytest.mark.asyncio
async def test_5xx_retried_then_server_error():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="down")

    with pytest.raises(YouGileServerError):
        await _client(handler).list_projects()
    assert calls["n"] == 4  # 1 + 3 retries


@pytest.mark.asyncio
async def test_token_bucket_enforces_under_50_per_minute():
    sleeps: list[float] = []

    async def _sleep(s: float) -> None:
        sleeps.append(s)

    # Frozen clock: no refill, so the 51st acquire must wait.
    bucket = TokenBucket(50, time_fn=lambda: 0.0, sleep_fn=_sleep)
    for _ in range(50):
        await bucket.acquire()
    assert sleeps == []  # first 50 are free (burst capacity)
    await bucket.acquire()  # 51st
    assert len(sleeps) == 1 and sleeps[0] > 0  # had to wait for a refill
