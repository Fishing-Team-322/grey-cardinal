"""Тесты переброса и отмены задач из чата (фичи 1 и 2) + контекстное окно (фича 4)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select

from brain_api.api.routes import internal_telegram as it
from brain_api.application.agentic_tasks import InteractionMode
from brain_api.domain.enums import TaskStatus
from brain_api.infrastructure.db import models as m
from grey_cardinal_contracts import (
    TelegramCallbackEvent,
    TelegramChatInfo,
    TelegramMessageEvent,
    TelegramMessageRef,
    TelegramSender,
)

TG_CHAT_ID = -100777000111
MANAGER_TG = 5001
PETYA_TG = 5002
ANYA_TG = 5003


class FakeContainer:
    """Минимальный контейнер: session_factory + заглушка board_mirror.

    board_mirror без нужных методов — синхронизация доски падает и гасится
    try/except в роутерах, что и проверяет, что board sync некритична.
    """

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.board_mirror = SimpleNamespace()


async def _seed(session_factory):
    """Компания, команда, чат, участники (manager/2 employee), одна задача GC-1 на Петю."""
    async with session_factory() as session:
        director = m.UserModel(id=uuid4(), display_name="Director", telegram_user_id=9001)
        manager = m.UserModel(id=uuid4(), display_name="Manager", telegram_user_id=MANAGER_TG)
        petya = m.UserModel(
            id=uuid4(), display_name="Петя", telegram_username="petya", telegram_user_id=PETYA_TG
        )
        anya = m.UserModel(
            id=uuid4(), display_name="Аня", telegram_username="anya", telegram_user_id=ANYA_TG
        )
        session.add_all([director, manager, petya, anya])
        await session.flush()

        company = m.CompanyModel(
            id=uuid4(), name="Acme", timezone="Europe/Moscow", created_by=director.id
        )
        session.add(company)
        await session.flush()
        session.add(
            m.CompanyAdminModel(
                id=uuid4(), company_id=company.id, user_id=director.id, role="director"
            )
        )
        team = m.TeamModel(
            id=uuid4(),
            company_id=company.id,
            name="Dev",
            timezone="Europe/Moscow",
            tg_chat_id=TG_CHAT_ID,
            board_provider="mock",
        )
        session.add(team)
        await session.flush()
        session.add_all(
            [
                m.TeamMemberModel(team_id=team.id, user_id=manager.id, role="manager"),
                m.TeamMemberModel(team_id=team.id, user_id=petya.id, role="employee"),
                m.TeamMemberModel(team_id=team.id, user_id=anya.id, role="employee"),
            ]
        )
        chat = m.TelegramChatModel(
            id=uuid4(), team_id=team.id, telegram_chat_id=TG_CHAT_ID, type="supergroup"
        )
        session.add(chat)
        await session.flush()
        task = m.TaskModel(
            id=uuid4(),
            seq=1,
            public_id="GC-1",
            team_id=team.id,
            title="Автоматизация API",
            status=TaskStatus.todo.value,
            priority="medium",
            assignee_id=petya.id,
            assignee_text="Петя",
            source="telegram_chat",
        )
        session.add(task)
        await session.commit()
        return {
            "team_id": team.id,
            "chat_db_id": chat.id,
            "task_id": task.id,
            "petya_id": petya.id,
            "anya_id": anya.id,
            "manager_id": manager.id,
        }


async def _add_message(session, chat_db_id, sender_id, text, *, tg_msg_id=900):
    msg = m.ChatMessageModel(
        id=uuid4(),
        telegram_message_id=tg_msg_id,
        chat_id=chat_db_id,
        sender_id=sender_id,
        sender_telegram_user_id=PETYA_TG,
        text=text,
        raw_json={},
    )
    session.add(msg)
    await session.flush()
    return msg


def _msg_event(text, *, sender_id=PETYA_TG, msg_id=900):
    return TelegramMessageEvent(
        update_id=1,
        message_id=msg_id,
        chat=TelegramChatInfo(id=TG_CHAT_ID, type="supergroup"),
        sender=TelegramSender(id=sender_id, username="petya", first_name="Петя"),
        text=text,
        date=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )


# ── Heuristics (pure) ─────────────────────────────────────────────────────────


def test_reassignment_heuristic_matches():
    assert it._detect_reassignment_heuristic("Задачу по API будет делать Кирилл")
    assert it._detect_reassignment_heuristic("Я буду делать задачу по автоматизации")
    assert it._detect_reassignment_heuristic("переназначь GC-17 на Аню")
    assert not it._detect_reassignment_heuristic("создай задачу по API на Кирилла")
    assert not it._detect_reassignment_heuristic("эта задача неактуальна")


def test_cancellation_heuristic_matches():
    assert it._detect_cancellation_heuristic("Эта задача по API неактуальна")
    assert it._detect_cancellation_heuristic("GC-17 неактуальна")
    assert it._detect_cancellation_heuristic("отмени задачу по автоматизации")
    assert not it._detect_cancellation_heuristic("создай задачу")
    assert not it._detect_cancellation_heuristic("я сделал задачу")


# ── Task resolution ───────────────────────────────────────────────────────────


async def test_resolve_task_by_gc_id(session_factory):
    seed = await _seed(session_factory)
    async with session_factory() as session:
        msg = await _add_message(session, seed["chat_db_id"], seed["petya_id"], "GC-1 неактуальна")
        task = await it._resolve_task_from_message(
            session, seed["team_id"], msg, "GC-1 неактуальна"
        )
    assert task is not None and task.public_id == "GC-1"


async def test_resolve_task_by_keywords(session_factory):
    seed = await _seed(session_factory)
    async with session_factory() as session:
        msg = await _add_message(
            session, seed["chat_db_id"], seed["petya_id"], "задача по автоматизации неактуальна"
        )
        task = await it._resolve_task_from_message(
            session, seed["team_id"], msg, "автоматизации API"
        )
    assert task is not None and task.public_id == "GC-1"


async def test_resolve_task_from_recent_window(session_factory):
    seed = await _seed(session_factory)
    async with session_factory() as session:
        msg = await _add_message(session, seed["chat_db_id"], seed["petya_id"], "эта неактуальна")
        recent = [{"sender": "Петя", "text": "смотрите GC-1 тут"}]
        task = await it._resolve_task_from_message(
            session, seed["team_id"], msg, "эта неактуальна", recent
        )
    assert task is not None and task.public_id == "GC-1"


# ── Reassignment ──────────────────────────────────────────────────────────────


async def test_reassignment_autonomous_changes_assignee(session_factory):
    seed = await _seed(session_factory)
    container = FakeContainer(session_factory)
    parsed = {
        "kind": "task_reassignment",
        "confidence": 0.9,
        "reassignment": {
            "task_reference": "GC-1",
            "new_assignee_reference": "Аня",
            "new_assignee_reference_type": "name",
        },
    }
    async with session_factory() as session:
        team = await session.get(m.TeamModel, seed["team_id"])
        sender = await session.get(m.UserModel, seed["petya_id"])
        msg = await _add_message(
            session, seed["chat_db_id"], seed["petya_id"], "GC-1 будет делать Аня"
        )
        resp = await it._route_v2_reassignment(
            session, container, team, sender, msg, parsed,
            _msg_event("GC-1 будет делать Аня"), [], InteractionMode.AUTO_BACKGROUND,
            autonomous=True,
        )
    assert any("переброшена" in a.text for a in resp.actions if hasattr(a, "text"))
    async with session_factory() as session:
        task = await session.get(m.TaskModel, seed["task_id"])
        assert task.assignee_id == seed["anya_id"]


async def test_reassignment_self_assignment_to_sender(session_factory):
    """«Я буду делать задачу по API» → исполнитель = автор сообщения."""
    seed = await _seed(session_factory)
    container = FakeContainer(session_factory)
    parsed = {
        "kind": "task_reassignment",
        "confidence": 0.9,
        "reassignment": {
            "task_reference": "автоматизация API",
            "new_assignee_reference": "я",
            "new_assignee_reference_type": "pronoun",
        },
    }
    async with session_factory() as session:
        team = await session.get(m.TeamModel, seed["team_id"])
        sender = await session.get(m.UserModel, seed["anya_id"])  # Аня берёт на себя
        msg = await _add_message(
            session, seed["chat_db_id"], seed["anya_id"],
            "Я буду делать задачу по автоматизации API",
        )
        resp = await it._route_v2_reassignment(
            session, container, team, sender, msg, parsed,
            _msg_event("Я буду делать задачу по автоматизации API", sender_id=ANYA_TG),
            [], InteractionMode.AUTO_BACKGROUND, autonomous=True,
        )
    assert resp.actions
    async with session_factory() as session:
        task = await session.get(m.TaskModel, seed["task_id"])
        assert task.assignee_id == seed["anya_id"]


async def test_reassignment_confirmation_creates_pending(session_factory):
    seed = await _seed(session_factory)
    container = FakeContainer(session_factory)
    parsed = {
        "kind": "task_reassignment",
        "confidence": 0.9,
        "reassignment": {"task_reference": "GC-1", "new_assignee_reference": "Аня"},
    }
    async with session_factory() as session:
        team = await session.get(m.TeamModel, seed["team_id"])
        sender = await session.get(m.UserModel, seed["petya_id"])
        msg = await _add_message(
            session, seed["chat_db_id"], seed["petya_id"], "GC-1 будет делать Аня"
        )
        resp = await it._route_v2_reassignment(
            session, container, team, sender, msg, parsed,
            _msg_event("GC-1 будет делать Аня"), [], InteractionMode.AUTO_BACKGROUND,
            autonomous=False,
        )
    kb = resp.actions[0].reply_markup["inline_keyboard"]
    assert kb[0][0]["callback_data"].startswith("chatact:confirm:")
    async with session_factory() as session:
        pending = await session.scalar(select(m.PendingChatActionModel))
        assert pending is not None and pending.kind == "reassign"
        # Задача ещё НЕ переназначена до подтверждения.
        task = await session.get(m.TaskModel, seed["task_id"])
        assert task.assignee_id == seed["petya_id"]


async def test_chatact_confirm_requires_manager(session_factory):
    seed = await _seed(session_factory)
    container = FakeContainer(session_factory)
    async with session_factory() as session:
        pending = m.PendingChatActionModel(
            id=uuid4(),
            team_id=seed["team_id"],
            kind="reassign",
            task_id=seed["task_id"],
            target_user_id=seed["anya_id"],
            requested_by_user_id=seed["petya_id"],
            status="pending",
            telegram_chat_id=TG_CHAT_ID,
            payload={"task_public_id": "GC-1", "new_assignee_name": "Аня"},
        )
        session.add(pending)
        await session.commit()
        pending_id = pending.id

    def _cb(from_tg):
        return TelegramCallbackEvent(
            update_id=2,
            callback_query_id="cq1",
            from_user=TelegramSender(id=from_tg, username="x"),
            message=TelegramMessageRef(message_id=900, chat_id=TG_CHAT_ID),
            data=f"chatact:confirm:{pending_id}",
        )

    # Сотрудник (employee) — нельзя.
    resp = await it._handle_chatact_callback(container, _cb(PETYA_TG))
    assert "руководитель" in resp.actions[0].text.lower()
    async with session_factory() as session:
        task = await session.get(m.TaskModel, seed["task_id"])
        assert task.assignee_id == seed["petya_id"]  # не изменилось

    # Менеджер — можно.
    resp = await it._handle_chatact_callback(container, _cb(MANAGER_TG))
    async with session_factory() as session:
        task = await session.get(m.TaskModel, seed["task_id"])
        assert task.assignee_id == seed["anya_id"]
        pending = await session.get(m.PendingChatActionModel, pending_id)
        assert pending.status == "confirmed"


# ── Cancellation ──────────────────────────────────────────────────────────────


async def test_cancellation_autonomous_sets_cancelled(session_factory):
    seed = await _seed(session_factory)
    container = FakeContainer(session_factory)
    parsed = {
        "kind": "task_cancellation",
        "confidence": 0.9,
        "cancellation": {"task_reference": "GC-1"},
    }
    async with session_factory() as session:
        team = await session.get(m.TeamModel, seed["team_id"])
        sender = await session.get(m.UserModel, seed["petya_id"])
        msg = await _add_message(session, seed["chat_db_id"], seed["petya_id"], "GC-1 неактуальна")
        resp = await it._route_v2_cancellation(
            session, container, team, sender, msg, parsed,
            _msg_event("GC-1 неактуальна"), [], autonomous=True,
        )
    assert any("отменена" in a.text for a in resp.actions if hasattr(a, "text"))
    async with session_factory() as session:
        task = await session.get(m.TaskModel, seed["task_id"])
        assert task.status == TaskStatus.cancelled.value


async def test_cancellation_confirmation_and_manager_confirm(session_factory):
    seed = await _seed(session_factory)
    container = FakeContainer(session_factory)
    parsed = {
        "kind": "task_cancellation",
        "confidence": 0.9,
        "cancellation": {"task_reference": "GC-1"},
    }
    async with session_factory() as session:
        team = await session.get(m.TeamModel, seed["team_id"])
        sender = await session.get(m.UserModel, seed["petya_id"])
        msg = await _add_message(session, seed["chat_db_id"], seed["petya_id"], "GC-1 неактуальна")
        resp = await it._route_v2_cancellation(
            session, container, team, sender, msg, parsed,
            _msg_event("GC-1 неактуальна"), [], autonomous=False,
        )
    kb = resp.actions[0].reply_markup["inline_keyboard"]
    cb_data = kb[0][0]["callback_data"]
    assert cb_data.startswith("chatact:confirm:")
    async with session_factory() as session:
        task = await session.get(m.TaskModel, seed["task_id"])
        assert task.status == TaskStatus.todo.value  # ещё не отменена

    cb = TelegramCallbackEvent(
        update_id=3,
        callback_query_id="cq2",
        from_user=TelegramSender(id=MANAGER_TG, username="mgr"),
        message=TelegramMessageRef(message_id=900, chat_id=TG_CHAT_ID),
        data=cb_data,
    )
    await it._handle_chatact_callback(container, cb)
    async with session_factory() as session:
        task = await session.get(m.TaskModel, seed["task_id"])
        assert task.status == TaskStatus.cancelled.value


async def test_chatact_confirm_idempotent(session_factory):
    seed = await _seed(session_factory)
    container = FakeContainer(session_factory)
    async with session_factory() as session:
        pending = m.PendingChatActionModel(
            id=uuid4(),
            team_id=seed["team_id"],
            kind="cancel",
            task_id=seed["task_id"],
            requested_by_user_id=seed["petya_id"],
            status="confirmed",  # уже обработано
            telegram_chat_id=TG_CHAT_ID,
            payload={"task_public_id": "GC-1"},
        )
        session.add(pending)
        await session.commit()
        pending_id = pending.id
    cb = TelegramCallbackEvent(
        update_id=4,
        callback_query_id="cq3",
        from_user=TelegramSender(id=MANAGER_TG, username="mgr"),
        message=TelegramMessageRef(message_id=900, chat_id=TG_CHAT_ID),
        data=f"chatact:confirm:{pending_id}",
    )
    resp = await it._handle_chatact_callback(container, cb)
    assert "обработано" in resp.actions[0].text.lower()


# ── Context window (фича 4) ───────────────────────────────────────────────────


async def test_recent_chat_window_collects_messages(session_factory):
    seed = await _seed(session_factory)
    async with session_factory() as session:
        await _add_message(session, seed["chat_db_id"], seed["petya_id"], "первое", tg_msg_id=1)
        await _add_message(session, seed["chat_db_id"], seed["petya_id"], "второе", tg_msg_id=2)
        current = await _add_message(
            session, seed["chat_db_id"], seed["petya_id"], "текущее", tg_msg_id=3
        )
        window = await it._recent_chat_window(session, seed["chat_db_id"], before_message=current)
    texts = [w["text"] for w in window]
    assert "первое" in texts and "второе" in texts
    assert "текущее" not in texts  # текущее сообщение исключено
