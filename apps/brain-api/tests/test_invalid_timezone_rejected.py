from fastapi import HTTPException

from brain_api.domain.v2.timezones import validate_iana_timezone


def test_invalid_timezone_rejected():
    try:
        validate_iana_timezone("Mars/Phobos")
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("invalid timezone was accepted")


def test_valid_timezone_is_returned():
    assert validate_iana_timezone("Europe/Moscow") == "Europe/Moscow"
