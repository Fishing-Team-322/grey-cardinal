"""Тесты предиктивного радара выгорания (Bucket B)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from brain_api.application.use_cases import burnout_forecast as bf
from brain_api.infrastructure.db import models as m

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


# ── Pure scoring ──────────────────────────────────────────────────────────────


def test_burnout_risk_rising_trend_higher_than_flat():
    flat = bf.burnout_risk(
        current_stress=0.5, stress_slope=0.0, overdue_ratio=0.0, overload_factor=0.0
    )
    rising = bf.burnout_risk(
        current_stress=0.5, stress_slope=0.05, overdue_ratio=0.0, overload_factor=0.0
    )
    assert rising > flat
    assert 0.0 <= rising <= 1.0


def test_risk_level_thresholds():
    assert bf.risk_level(0.1) == "ok"
    assert bf.risk_level(0.45) == "watch"
    assert bf.risk_level(0.65) == "high"
    assert bf.risk_level(0.9) == "critical"


def test_eta_days_projects_threshold():
    # стресс 0.5, растёт на 0.05/день → порог 0.75 через ~5 дней
    assert bf.eta_days(0.5, 0.05) == 5
    # не растёт → None
    assert bf.eta_days(0.5, 0.0) is None
    # уже за порогом → 0
    assert bf.eta_days(0.8, 0.05) == 0


def test_slope_detects_rising_series():
    rising = bf._slope_per_day([0.1, 0.1, 0.2, 0.3, 0.6, 0.7, 0.8])
    falling = bf._slope_per_day([0.8, 0.7, 0.6, 0.3, 0.2, 0.1, 0.1])
    assert rising > 0 > falling


# ── DB forecast ───────────────────────────────────────────────────────────────


async def _seed(session):
    director = m.UserModel(id=uuid4(), display_name="Dir")
    anya = m.UserModel(id=uuid4(), display_name="Аня", telegram_user_id=6001)
    petya = m.UserModel(id=uuid4(), display_name="Петя", telegram_user_id=6002)
    session.add_all([director, anya, petya])
    await session.flush()
    company = m.CompanyModel(id=uuid4(), name="A", timezone="UTC", created_by=director.id)
    session.add(company)
    await session.flush()
    team = m.TeamModel(
        id=uuid4(), company_id=company.id, name="Dev", timezone="UTC", board_provider="mock",
    )
    session.add(team)
    await session.flush()
    session.add_all([
        m.TeamMemberModel(team_id=team.id, user_id=anya.id, role="employee"),
        m.TeamMemberModel(team_id=team.id, user_id=petya.id, role="employee"),
    ])
    # Аня: стресс растёт последние дни (тренд к выгоранию).
    for days_ago, stress in [(10, 0.2), (8, 0.3), (5, 0.45), (3, 0.6), (1, 0.7), (0, 0.78)]:
        session.add(m.EmotionSignalModel(
            id=uuid4(), team_id=team.id, user_id=anya.id, source="chat_text",
            valence=-0.4, stress=stress, confidence=0.6,
            created_at=NOW - timedelta(days=days_ago),
        ))
    # Петя: стабильно спокоен.
    for days_ago in (6, 4, 2, 0):
        session.add(m.EmotionSignalModel(
            id=uuid4(), team_id=team.id, user_id=petya.id, source="chat_text",
            valence=0.2, stress=0.15, confidence=0.6,
            created_at=NOW - timedelta(days=days_ago),
        ))
    await session.commit()
    return {"team_id": team.id, "anya_id": anya.id}


async def test_forecast_flags_rising_member(session_factory):
    async with session_factory() as session:
        seed = await _seed(session)
        forecasts = await bf.forecast_team(session, seed["team_id"], now=NOW)
    assert forecasts[0].user_id == seed["anya_id"]  # худший — первый
    anya = forecasts[0]
    assert anya.level in ("high", "critical")
    assert anya.trend == "растёт"
    assert "стресс растёт" in anya.drivers
    summary = bf.team_burnout_summary(forecasts)
    assert summary["at_risk_count"] >= 1
    assert summary["top"] == "Аня"


async def test_forecast_render_text(session_factory):
    async with session_factory() as session:
        seed = await _seed(session)
        forecasts = await bf.forecast_team(session, seed["team_id"], now=NOW)
    text = bf.render_forecast_text(forecasts)
    assert "Радар выгорания" in text and "Аня" in text


def test_render_text_calm_team():
    assert "норме" in bf.render_forecast_text([])
