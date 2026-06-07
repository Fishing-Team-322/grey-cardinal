"""Item 10: naive datetime от LLM трактуется в таймзоне команды, а не в UTC."""

from brain_api.api.routes.internal_telegram import _parse_dt


def test_naive_moscow_converts_to_utc():
    # 18:00 по Москве (UTC+3) -> 15:00 UTC
    dt = _parse_dt("2026-06-06T18:00:00", "Europe/Moscow")
    assert dt is not None
    assert dt.utcoffset().total_seconds() == 0
    assert (dt.hour, dt.minute) == (15, 0)


def test_naive_dubai_converts_to_utc():
    # 18:00 по Дубаю (UTC+4) -> 14:00 UTC
    dt = _parse_dt("2026-06-06T18:00:00", "Asia/Dubai")
    assert (dt.hour, dt.minute) == (14, 0)


def test_aware_datetime_preserved():
    dt = _parse_dt("2026-06-06T18:00:00+00:00", "Europe/Moscow")
    assert (dt.hour, dt.minute) == (18, 0)


def test_invalid_timezone_falls_back_to_utc():
    dt = _parse_dt("2026-06-06T18:00:00", "Not/AZone")
    assert (dt.hour, dt.minute) == (18, 0)
