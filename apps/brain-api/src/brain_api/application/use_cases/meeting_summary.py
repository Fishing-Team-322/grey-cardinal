"""Meeting summaries + shareable public pages.

Builds a concise summary of a meeting from its transcript events and the tasks
extracted from it, stores it on the meeting, and creates a token-gated public
share link so the bot can post a short message + URL to the chat (instead of a
wall of text).
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from brain_api.config import Settings
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.llm.client import OpenAICompatibleClient

logger = logging.getLogger(__name__)

_SYS = (
    "Ты — ассистент, который кратко резюмирует рабочие созвоны на русском. "
    "Верни строго JSON с полями: summary (1-3 предложения), highlights (массив "
    "коротких пунктов), decisions (массив решений), action_items (массив строк)."
)


def public_base(settings: Settings) -> str:
    return (
        getattr(settings, "public_base_url", "")
        or getattr(settings, "telegram_public_base_url", "")
        or "https://fishingteam.su"
    ).rstrip("/")


def _llm(settings: Settings) -> OpenAICompatibleClient | None:
    try:
        if not settings.llm_enabled:
            return None
        return OpenAICompatibleClient(
            base_url=settings.effective_llm_base_url,
            api_key=settings.effective_llm_api_key,
            model=settings.llm_model,
            timeout=float(getattr(settings, "llm_timeout_seconds", 60) or 60),
        )
    except Exception:
        return None


async def _transcript_lines(session, meeting_id: UUID) -> list[str]:
    rows = list(
        await session.scalars(
            select(m.TranscriptEventModel)
            .where(m.TranscriptEventModel.meeting_db_id == meeting_id)
            .order_by(m.TranscriptEventModel.ts.asc())
            .limit(2000)
        )
    )
    out = []
    for r in rows:
        speaker = r.speaker_name or r.speaker_id or "—"
        text = (r.text or "").strip()
        if text:
            out.append(f"{speaker}: {text}")
    return out


async def build_summary_payload(session, settings: Settings, meeting: m.MeetingModel) -> dict:
    lines = await _transcript_lines(session, meeting.id)
    transcript = "\n".join(lines)
    title = meeting.title or "Созвон"
    when = meeting.scheduled_at or meeting.started_at

    summary, highlights, decisions, action_items = "", [], [], []
    if transcript:
        client = _llm(settings)
        if client is not None:
            try:
                raw = await client.chat(_SYS, f"Созвон «{title}». Транскрипт:\n{transcript[:8000]}")
                data = json.loads(raw)
                summary = str(data.get("summary") or "")
                highlights = [str(x) for x in (data.get("highlights") or [])][:10]
                decisions = [str(x) for x in (data.get("decisions") or [])][:10]
                action_items = [str(x) for x in (data.get("action_items") or [])][:10]
            except Exception as exc:  # noqa: BLE001
                logger.warning("meeting summary LLM failed: %s", exc)
        if not summary:
            # Heuristic fallback: first lines + speakers.
            speakers = sorted({ln.split(":", 1)[0] for ln in lines})
            summary = (
                f"Созвон «{title}». Участников: {len(speakers)}. "
                f"Реплик в транскрипте: {len(lines)}."
            )
            highlights = lines[:8]
    else:
        summary = "Транскрипт созвона пока не записан. Запустите десктоп-агент во время встречи."

    return {
        "title": title,
        "when": when.isoformat() if when else None,
        "summary": summary,
        "highlights": highlights,
        "decisions": decisions,
        "action_items": action_items,
        "transcript_lines": len(lines),
    }


async def create_share_link(
    session,
    *,
    kind: str,
    team_id: UUID | None,
    ref_id: UUID | None,
    title: str | None,
    payload: dict,
) -> str:
    token = secrets.token_urlsafe(16)
    session.add(
        m.ShareLinkModel(
            token=token,
            kind=kind,
            team_id=team_id,
            ref_id=ref_id,
            title=title,
            payload=payload,
            created_at=datetime.now(UTC),
        )
    )
    return token


async def generate_meeting_summary(
    session, settings: Settings, meeting: m.MeetingModel
) -> dict:
    """Build summary, persist on meeting, create share link. Returns dict with url."""
    payload = await build_summary_payload(session, settings, meeting)
    meeting.summary = payload["summary"]
    token = await create_share_link(
        session,
        kind="meeting",
        team_id=meeting.team_id,
        ref_id=meeting.id,
        title=payload["title"],
        payload=payload,
    )
    url = f"{public_base(settings)}/s.html?t={token}"
    return {"token": token, "url": url, **payload}
