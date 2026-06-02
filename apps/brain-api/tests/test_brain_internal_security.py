from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from brain_api.api.deps import verify_internal_token


def _request():
    settings = SimpleNamespace(internal_api_token="secret")
    container = SimpleNamespace(settings=settings)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=container)))


async def test_internal_endpoint_token_is_required():
    with pytest.raises(HTTPException) as exc:
        await verify_internal_token(_request(), None)
    assert exc.value.status_code == 401


async def test_internal_endpoint_rejects_wrong_token():
    with pytest.raises(HTTPException) as exc:
        await verify_internal_token(_request(), "wrong")
    assert exc.value.status_code == 401


async def test_internal_endpoint_accepts_correct_token():
    await verify_internal_token(_request(), "secret")
