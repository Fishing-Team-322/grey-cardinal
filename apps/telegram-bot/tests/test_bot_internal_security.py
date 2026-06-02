from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from telegram_bot.main import _verify_internal


def _request():
    settings = SimpleNamespace(internal_api_token="secret")
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))


def test_internal_endpoint_token_is_required():
    with pytest.raises(HTTPException) as exc:
        _verify_internal(_request(), None)
    assert exc.value.status_code == 401


def test_internal_endpoint_rejects_wrong_token():
    with pytest.raises(HTTPException) as exc:
        _verify_internal(_request(), "wrong")
    assert exc.value.status_code == 401


def test_internal_endpoint_accepts_correct_token():
    _verify_internal(_request(), "secret")
