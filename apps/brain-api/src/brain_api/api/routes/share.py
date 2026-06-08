"""Public, token-gated share pages (meeting summaries, digests).

No authentication: the unguessable token IS the capability. Used so the bot can
post a short message + link to a chat instead of a wall of text.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.routes.accounts import get_db
from brain_api.infrastructure.db import models as m

router = APIRouter(prefix="/api/public", tags=["public-share"])


@router.get("/share/{token}")
async def get_share(token: str, session: AsyncSession = Depends(get_db)) -> dict:
    row = await session.scalar(select(m.ShareLinkModel).where(m.ShareLinkModel.token == token))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    if row.expires_at is not None:
        exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
        if exp < datetime.now(UTC):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "expired")
    return {
        "kind": row.kind,
        "title": row.title,
        "payload": row.payload,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
