"""Тесты /help (материалы) и /settings (расписание дайджеста)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from brain_api.application.use_cases import task_help, team_settings
from brain_api.application.use_cases.team_digest import run_team_digests
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.telegram_gateway.client import NullTelegramGateway
from grey_cardinal_contracts import TelegramCallbackEvent, TelegramMessageRef, TelegramSender

CHAT = -100555


# ── task_help ────────────────────────────────────────────────────────────────

def test_clean_topic_strips_prefixes():
    assert task_help.clean_topic("помощь по задаче написать API") == "написать API"
    assert task_help.clean_topic("как сделать авторизацию JWT") == "авторизацию JWT"


def test_build_materials_has_links():
    text = task_help.build_materials("написать REST API")
    assert "youtube.com/results" in text
    assert "habr.com" in text
    assert "stackoverflow.com" in text


def test_is_help_request_text():
    assert task_help.is_help_request_text("помощь по задаче X")
    assert not task_help.is_help_request_text("привет как дела")  # "как дела" не триггер


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Кардинал нам нужен созвон", "нам нужен созвон"),
        ("кардинал, задача для Дениса", "задача для Дениса"),
        ("Серый Кардинал: создай задачу", "создай задачу"),
        ("  КАРДИНАЛ — нужен созвон", "нужен созвон"),
        ("Координату запланирую встречу на 12.0", "запланирую встречу на 12.0"),
        ("Dinal нам нужен созвон 12.30", "нам нужен созвон 12.30"),
        ("Cardinal сделается созвон 12-30", "сделается созвон 12-30"),
        ("Так, Cardinal, мне срочно нужен созвон на 12.30", "мне срочно нужен созвон на 12.30"),
        ("кординал надо сделать задачу", "надо сделать задачу"),
        ("кардинальный вопрос", None),
        ("нам нужен созвон", None),
        ("Кардинал", None),
    ],
)
def test_addressed_message_text(text, expected):
    assert team_settings.addressed_message_text(text, required=True) == expected


def test_addressed_message_text_disabled_keeps_original():
    text = "нам нужен созвон"
    assert team_settings.addressed_message_text(text, required=False) == text


@pytest.mark.asyncio
async def test_materials_for_gc_id(session_factory):
    async with session_factory() as session:
        session.add(m.TaskModel(
            seq=1, public_id="GC-1", title="Поднять websocket для дашборда",
            status="todo", priority="medium", source="telegram_chat",
        ))
        await session.commit()
        text = await task_help.materials_for_arg(session, "GC-1")
    assert "websocket" in text.lower()


# ── team_settings ────────────────────────────────────────────────────────────

async def _seed_team(session, digest_mode=None):
    company = m.CompanyModel(name="Co", timezone="Europe/Moscow", created_by=uuid4())
    session.add(company)
    await session.flush()
    cfg = {"digest_mode": digest_mode} if digest_mode else {}
    team = m.TeamModel(company_id=company.id, name="T", timezone="Europe/Moscow",
                       tg_chat_id=CHAT, board_config=cfg)
    session.add(team)
    await session.flush()
    return team


def _cb(data):
    return TelegramCallbackEvent(
        update_id=1, callback_query_id="cq",
        from_user=TelegramSender(id=1, username="u", first_name="U"),
        message=TelegramMessageRef(message_id=5, chat_id=CHAT), data=data,
    )


@pytest.mark.asyncio
async def test_settings_open_and_set(session_factory):
    async with session_factory() as session:
        await _seed_team(session)
        await session.commit()
        opened = await team_settings.open_settings(session, CHAT)
        kb = opened.actions[0].reply_markup
        cbs = [b["callback_data"] for row in kb["inline_keyboard"] for b in row]
        assert any(c == "cfg_dig:both" for c in cbs)
        assert team_settings.CB_SET_CARDINAL_MENTION in cbs
        # set mode
        ev = _cb("cfg_dig:both")
        resp = await team_settings.handle_settings_callback(session, "cfg_dig:both", ev)
        team = await session.scalar(
            select(m.TeamModel).where(m.TeamModel.tg_chat_id == CHAT)
        )
        assert team.board_config["digest_mode"] == "both"
    assert any(a.type == "answer_callback" for a in resp.actions)


@pytest.mark.asyncio
async def test_settings_toggle_cardinal_mention(session_factory):
    async with session_factory() as session:
        await _seed_team(session)
        await session.commit()
        ev = _cb(team_settings.CB_SET_CARDINAL_MENTION)
        resp = await team_settings.handle_settings_callback(
            session,
            team_settings.CB_SET_CARDINAL_MENTION,
            ev,
        )
        team = await session.scalar(
            select(m.TeamModel).where(m.TeamModel.tg_chat_id == CHAT)
        )
        assert team.board_config["require_cardinal_mention"] is True
        assert "только после" in resp.actions[1].text


@pytest.mark.asyncio
async def test_settings_no_team(session_factory):
    async with session_factory() as session:
        resp = await team_settings.open_settings(session, -999)
    assert "привяж" in resp.actions[0].text.lower()


# ── team_digest ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_team_digest_sends_at_slot_and_dedups(session_factory):
    async with session_factory() as session:
        team = await _seed_team(session, digest_mode="both")  # slots [9,20]
        session.add(m.TaskModel(
            seq=1, public_id="GC-1", title="Сделать оплату", status="todo",
            priority="medium", source="telegram_chat", team_id=team.id,
        ))
        await session.commit()
    gateway = NullTelegramGateway()
    # 09:00 Moscow == 06:00 UTC
    now = datetime(2026, 6, 8, 6, 5, tzinfo=UTC)
    sent = await run_team_digests(session_factory, gateway, now=now)
    assert sent == 1
    assert gateway.sent[0][0] == CHAT
    assert "GC-1" in gateway.sent[0][1]
    # повторный прогон в тот же слот — без дубля
    sent2 = await run_team_digests(session_factory, gateway, now=now)
    assert sent2 == 0
