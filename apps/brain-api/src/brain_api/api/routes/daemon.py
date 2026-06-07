"""Daemon (desktop-agent) state endpoint — production, tenant-scoped.

Заменяет небезопасный `/api/session/current` (без auth, глобальный single-tenant)
для основного поллинга демона. Демон спрашивает «можно ли сейчас записывать?»:

    GET /api/daemon/state
    X-Agent-Token: <client_session_id, выданный при register_device>

Ответ привязан к встречам команд, в которых состоит пользователь демона. Демон
включается только в окне созвона:

    idle      — встреч нет / ещё рано / уже поздно
    armed     — за MEETING_ARM_MINUTES_BEFORE минут до начала (пора готовиться)
    recording — идёт время созвона (scheduled_at .. scheduled_at+duration)

Состояние считается из времени встречи, поэтому работает даже без отдельного
scheduler'а, который персистит переходы (см. будущий meeting state-machine).
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy import select

from brain_api.api.deps import get_container
from brain_api.api.routes.accounts import CurrentUser, get_db
from brain_api.application.agentic_tasks import IdentityResolver, InteractionMode
from brain_api.application.rendering import proposal_keyboard
from brain_api.application.semantic_parser import SemanticMessageInput
from brain_api.config import get_settings
from brain_api.container import Container
from brain_api.domain.enums import TaskSource
from brain_api.infrastructure.db import models as m

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/daemon", tags=["daemon"])

_ACTIVE_MEETING_STATES = ("scheduled", "armed", "recording")
_DEAD_SESSION_STATUSES = ("revoked", "expired")


class DaemonAuthError(Exception):
    """Невалидный/просроченный agent-token."""


def _extract_token(x_agent_token: str | None, authorization: str | None) -> str | None:
    if x_agent_token:
        return x_agent_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


@router.get("/state")
async def daemon_state(
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    authorization: str | None = Header(default=None),
    container: Container = Depends(get_container),
) -> dict:
    token = _extract_token(x_agent_token, authorization)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing agent token")
    settings = get_settings()
    now = datetime.now(UTC)
    async with container.session_factory() as session:
        try:
            return await resolve_daemon_state(session, token, now, settings)
        except DaemonAuthError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid agent token") from exc


async def resolve_daemon_state(session, token: str, now: datetime, settings) -> dict:
    client_session = await _resolve_session(session, token)
    if client_session is None:
        raise DaemonAuthError()
    team_ids = await _user_team_ids(session, client_session.user_id)
    meeting = await _pick_meeting(session, team_ids, now, settings) if team_ids else None
    if meeting is not None:
        team = await session.get(m.TeamModel, meeting.team_id)
        if team is not None and not (team.board_config or {}).get("daemon_autorecord", True):
            meeting = None  # команда отключила авто-запись даемоном
    state, recording_started_at = _compute_state(meeting, now, settings)
    return _payload(state, meeting, recording_started_at, now, settings)


async def _resolve_session(session, token: str):
    try:
        session_id = UUID(token)
    except (ValueError, AttributeError):
        return None
    cs = await session.get(m.ClientSessionModel, session_id)
    if cs is None or cs.status in _DEAD_SESSION_STATUSES:
        return None
    return cs


async def _user_team_ids(session, user_id: UUID) -> list[UUID]:
    rows = await session.execute(
        select(m.TeamMemberModel.team_id).where(m.TeamMemberModel.user_id == user_id)
    )
    return [r[0] for r in rows.all()]


async def _pick_meeting(session, team_ids: list[UUID], now: datetime, settings):
    """Ближайшая релевантная встреча команд пользователя (окно arm..end)."""
    default_duration = settings.meeting_default_duration_minutes
    window_start = now - timedelta(minutes=default_duration)
    window_end = now + timedelta(minutes=settings.meeting_arm_minutes_before)
    rows = await session.execute(
        select(m.MeetingModel)
        .where(
            m.MeetingModel.team_id.in_(team_ids),
            m.MeetingModel.state.in_(_ACTIVE_MEETING_STATES),
            m.MeetingModel.scheduled_at.is_not(None),
            m.MeetingModel.scheduled_at >= window_start,
            m.MeetingModel.scheduled_at <= window_end,
        )
        .order_by(m.MeetingModel.scheduled_at)
    )
    return rows.scalars().first()


def _compute_state(meeting, now: datetime, settings) -> tuple[str, datetime | None]:
    if meeting is None or meeting.scheduled_at is None:
        return "idle", None
    scheduled_at = _as_utc(meeting.scheduled_at)
    duration = meeting.duration_minutes or settings.meeting_default_duration_minutes
    arm_at = scheduled_at - timedelta(minutes=settings.meeting_arm_minutes_before)
    end_at = scheduled_at + timedelta(minutes=duration)
    if now < arm_at:
        return "idle", None
    if now < scheduled_at:
        return "armed", None
    if now < end_at:
        return "recording", scheduled_at
    return "idle", None


def _payload(state, meeting, recording_started_at, now: datetime, settings) -> dict:
    return {
        "state": state,
        "meeting_id": str(meeting.id) if meeting else None,
        "meeting_public_id": meeting.public_id if meeting else None,
        "team_id": str(meeting.team_id) if meeting and meeting.team_id else None,
        "scheduled_at": _as_utc(meeting.scheduled_at).isoformat()
        if meeting and meeting.scheduled_at
        else None,
        "recording_started_at": recording_started_at.isoformat()
        if recording_started_at
        else None,
        "max_duration_minutes": (
            meeting.duration_minutes if meeting and meeting.duration_minutes
            else settings.meeting_default_duration_minutes
        ),
        "server_time": now.isoformat(),
    }


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


# ── Agent pairing token (для ПК-агента, привязка к аккаунту пользователя) ─────

@router.post("/token")
async def issue_agent_token(
    current_user: CurrentUser,
    session=Depends(get_db),
) -> dict:
    """Выдать ПК-агенту токен, привязанный к аккаунту (= client_session_id).

    Пользователь генерирует токен в кабинете и вставляет его в трей-агент. Аплоады
    агента маршрутизируются в команды этого пользователя.
    """
    now = datetime.now(UTC)
    device = m.DeviceModel(
        user_id=current_user.id, device_name="PC Agent", platform="windows", last_seen_at=now
    )
    session.add(device)
    await session.flush()
    cs = m.ClientSessionModel(
        user_id=current_user.id, device_id=device.id, status="active", started_at=now
    )
    session.add(cs)
    await session.commit()
    return {"token": str(cs.id), "server_url": get_settings().telegram_public_base_url or ""}


# ── Daemon audio → v2 team task proposal ──────────────────────────────────────

@router.post("/v2/uploads")
async def daemon_v2_upload(
    audio: UploadFile | None = File(default=None),
    transcript_text: str = Form(default=""),
    duration_sec: float = Form(default=0),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
    container: Container = Depends(get_container),
) -> dict:
    """Аудио/транскрипт с ПК-агента → ASR → v2-семантика команды → proposal в чат.

    Auth: X-Agent-Token (client_session_id). Команда выбирается по пользователю
    агента (первая команда с привязанным Telegram-чатом).
    """
    token = _extract_token(x_agent_token, None)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing agent token")
    async with container.session_factory() as session:
        cs = await _resolve_session(session, token)
        if cs is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid agent token")
        team = await _agent_team(session, cs.user_id)
        team_id = team.id if team else None
    if team_id is None:
        return {"ok": True, "proposal_created": False, "detail": "no bound team"}

    text = (transcript_text or "").strip()
    if not text and audio is not None:
        content = await audio.read()
        text = await _transcribe_audio(content)
    if not text:
        return {"ok": True, "transcript": "", "proposal_created": False}

    result = await ingest_team_text(container, team_id, text, source=TaskSource.meeting_transcript)
    return {"ok": True, "transcript": text[:200], **result}


async def _agent_team(session, user_id: UUID):
    """Первая команда пользователя. Internal Grey Board does not require Telegram."""
    return await session.scalar(
        select(m.TeamModel)
        .join(m.TeamMemberModel, m.TeamMemberModel.team_id == m.TeamModel.id)
        .where(m.TeamMemberModel.user_id == user_id)
        .order_by(m.TeamMemberModel.joined_at)
    )


async def _transcribe_audio(content: bytes) -> str:
    url = os.getenv("ASR_SERVICE_URL", "http://asr-service:8030").rstrip("/") + "/transcribe"
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(url, content=content, headers={"Content-Type": "audio/wav"})
            r.raise_for_status()
            return (r.json().get("text") or "").strip()
    except Exception as exc:  # noqa: BLE001 — ASR ошибка не должна ронять аплоад
        logger.warning("daemon ASR failed: %s", exc)
        return ""


async def ingest_team_text(
    container: Container, team_id: UUID, text: str, source: TaskSource
) -> dict:
    """Прогнать текст через v2-семантику команды и при task_candidate создать
    proposal + AI Inbox item, затем при наличии отправить его в Telegram-чат."""
    from brain_api.api.routes.internal_telegram import (
        _find_v2_duplicate,
        _parse_dt,
    )

    now = datetime.now(UTC)
    async with container.session_factory() as session:
        team = await session.get(m.TeamModel, team_id)
        if team is None:
            return {"kind": "unknown", "proposal_created": False}
        members = list(
            (
                await session.execute(
                    select(m.UserModel)
                    .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
                    .where(m.TeamMemberModel.team_id == team.id)
                )
            ).scalars()
        )
        devices = list(
            (
                await session.execute(
                    select(m.DeviceModel, m.UserModel)
                    .join(m.UserModel, m.UserModel.id == m.DeviceModel.user_id)
                    .join(m.TeamMemberModel, m.TeamMemberModel.user_id == m.UserModel.id)
                    .where(m.TeamMemberModel.team_id == team.id)
                )
            ).all()
        )
        member_context = [
            " | ".join(
                value
                for value in (
                    user.display_name,
                    f"@{user.telegram_username}" if user.telegram_username else None,
                    user.login,
                    user.email,
                )
                if value
            )
            for user in members
        ]
        member_context.extend(
            f"{user.display_name} | Windows agent: {device.device_name}"
            for device, user in devices
        )
        try:
            parsed = await container.semantic_parser.parse(
                SemanticMessageInput(
                    team_id=team.id, message_text=text, sender_user_id=None,
                    team_timezone=team.timezone, now=now,
                    team_members=member_context,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("daemon semantic parse failed: %s", exc)
            return {"kind": "unknown", "proposal_created": False}

        kind = parsed["kind"]
        conf = float(parsed["confidence"])
        if kind != "task_candidate" or conf < container.config.task_extraction_min_confidence:
            return {"kind": kind, "proposal_created": False}

        task = parsed.get("task") or {}
        title = str(task.get("title") or text[:120]).strip()
        assignee_text = task.get("assignee_reference") or task.get("assignee_text")
        resolution = await IdentityResolver(session).resolve_assignee(
            team.id,
            assignee_text,
            [],
            text,
            None,
            InteractionMode.AUTO_BACKGROUND,
        )
        assignee = (
            await session.get(m.UserModel, resolution.user_id) if resolution.user_id else None
        )
        deadline = _parse_dt(task.get("deadline"), team.timezone)
        duplicate = await _find_v2_duplicate(
            session, team.id, title, assignee.id if assignee else None
        )
        if duplicate is not None:
            return {"kind": kind, "proposal_created": False, "duplicate": duplicate.public_id}

        proposal = m.TaskProposalModel(
            team_id=team.id, source=source.value, title=title, description=task.get("description"),
            assignee_text=assignee_text, assignee_id=assignee.id if assignee else None,
            deadline=deadline, deadline_timezone=team.timezone,
            priority=task.get("priority") or "medium", confidence=conf,
            raw_text=text, extractor_payload=parsed,
        )
        session.add(proposal)
        await session.flush()
        confirmation = m.ConfirmationModel(
            team_id=team.id, proposal_id=proposal.id, status="pending",
            telegram_chat_id=team.tg_chat_id,
        )
        session.add(confirmation)
        inbox_item = m.AIInboxItemModel(
            team_id=team.id,
            kind="task_candidate",
            status="pending",
            reason="windows_agent_proposal",
            raw_text=text,
            semantic_payload=parsed,
            identity_payload=resolution.payload(),
            item_type="task_proposal",
            source_type="daemon_proposal",
            source_id=str(proposal.id),
            source_text=text,
            proposed_action="approve",
            confidence=conf,
        )
        session.add(inbox_item)
        await session.commit()
        chat_id = team.tg_chat_id
        conf_id = confirmation.id
        inbox_id = inbox_item.id

    if chat_id is not None:
        msg = (
            "🎙 Из созвона — нашёл задачу\n\n"
            f"Что сделать:\n{title}\n\n"
            f"Исполнитель:\n{assignee_text or 'не указан'}\n\n"
            "Создать карточку?"
        )
        await container.telegram_gateway.send_message(chat_id, msg, proposal_keyboard(conf_id))
    return {
        "kind": kind,
        "proposal_created": True,
        "title": title,
        "ai_inbox_item_id": str(inbox_id),
    }
