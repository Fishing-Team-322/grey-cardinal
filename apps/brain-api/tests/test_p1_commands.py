from types import SimpleNamespace

from brain_api.api.routes.debug import dependencies, state
from brain_api.api.routes.internal_telegram import ingest_callback, ingest_command
from conftest import NOW
from grey_cardinal_contracts import (
    TelegramCallbackEvent,
    TelegramChatInfo,
    TelegramCommandEvent,
    TelegramMessageRef,
    TelegramSender,
)


def _event(command: str, chat_id: int = -100123456789) -> TelegramCommandEvent:
    return TelegramCommandEvent(
        update_id=1,
        message_id=1,
        chat=TelegramChatInfo(id=chat_id, type="supergroup", title="Hackathon Team"),
        sender=TelegramSender(id=111, username="petya", first_name="Петя"),
        command=command,
        text=f"/{command}",
        date=NOW,
    )


def _container(make_uow, config, extractor, telegram, events):
    return SimpleNamespace(
        make_uow=make_uow,
        config=config,
        extractor=extractor,
        telegram_gateway=telegram,
        event_publisher=events,
        settings=SimpleNamespace(
            app_env="dev",
            telegram_bot_base_url="http://telegram-bot:8010",
        ),
    )


async def test_bind_chat_and_demo_commands(make_uow, config, extractor, telegram, events):
    container = _container(make_uow, config, extractor, telegram, events)
    bound = await ingest_command(_event("bind_chat"), container)
    assert "Hackathon Team" in bound.actions[0].text

    started = await ingest_command(_event("demo_start"), container)
    assert "MTG-1" in started.actions[0].text

    status = await ingest_command(_event("meeting_status"), container)
    assert "Реплик: 3" in status.actions[0].text

    reset = await ingest_command(_event("demo_reset"), container)
    assert "Встреч: 1" in reset.actions[0].text


async def test_debug_state_and_dependencies(make_uow, config, extractor, telegram, events):
    container = _container(make_uow, config, extractor, telegram, events)
    counts = await state(container)
    assert counts["meetings"] == 0
    result = await dependencies(container)
    assert result["ok"] is True
    assert result["board_provider"] == "team-scoped"


async def test_bind_chat_replaces_previous_notification_chat(
    make_uow, config, extractor, telegram, events, seed_chat
):
    await seed_chat(-100111)
    container = _container(make_uow, config, extractor, telegram, events)

    await ingest_command(_event("bind_chat", -100222), container)

    async with make_uow() as uow:
        project = await uow.projects.ensure_default(config.default_workspace_name)
        assert project.default_chat_id is not None
        chat = await uow.chats.get(project.default_chat_id)
        assert chat is not None
        assert chat.telegram_chat_id == -100222


async def test_group_start_asks_confirmation_mode(make_uow, config, extractor, telegram, events):
    container = _container(make_uow, config, extractor, telegram, events)

    response = await ingest_command(_event("start"), container)

    keyboard = response.actions[0].reply_markup["inline_keyboard"]
    callbacks = [button["callback_data"] for row in keyboard for button in row]
    assert callbacks == ["mode:confirm", "mode:auto"]


async def test_confirmation_mode_callback_is_persisted(
    make_uow, config, extractor, telegram, events
):
    container = _container(make_uow, config, extractor, telegram, events)
    event = TelegramCallbackEvent(
        update_id=1,
        callback_query_id="cb-1",
        from_user=TelegramSender(id=111, username="petya", first_name="Петя"),
        message=TelegramMessageRef(message_id=10, chat_id=-100123456789),
        data="mode:auto",
    )

    response = await ingest_callback(event, container)

    assert response.actions[1].type == "edit_message"
    async with make_uow() as uow:
        chat = await uow.chats.get_by_telegram_id(-100123456789)
    assert chat is not None
    assert chat.task_confirmation_required is False
