"""User account management: registration, login, profile.

Endpoints:
  POST /api/auth/register   — create account
  POST /api/auth/login      — sign in, set httpOnly session cookie
  GET  /api/auth/me         — current user (requires auth)
  PATCH /api/auth/me        — update profile (requires auth)
  POST /api/auth/logout     — clear session cookie
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import parse_qsl
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from brain_api.api.deps import get_container
from brain_api.config import get_settings
from brain_api.container import Container
from brain_api.infrastructure.auth.jwt import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.db.models import UserModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["accounts"])

# ── Validation helpers ────────────────────────────────────────────────────────

_LOGIN_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{3,50}$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_email(v: str) -> str:
    v = v.strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("Invalid email address")
    return v


def _validate_login(v: str) -> str:
    v = v.strip().lower()
    if not _LOGIN_RE.match(v):
        raise ValueError("Login must be 3–50 chars: letters, digits, _ - .")
    return v


# ── Request / Response schemas ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    login: str
    first_name: str
    last_name: str
    password: str

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _validate_email(v)

    @field_validator("login")
    @classmethod
    def check_login(cls, v: str) -> str:
        return _validate_login(v)

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

    @field_validator("first_name", "last_name")
    @classmethod
    def check_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name fields cannot be empty")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _validate_email(v)


class UpdateProfileRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    bio: str | None = None
    photo_data_url: str | None = None
    role: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    login: str
    first_name: str
    last_name: str
    display_name: str
    bio: str
    photo_data_url: str
    role: str
    telegram_user_id: int | None = None
    telegram_username: str | None = None

    model_config = {"from_attributes": True}


class TelegramLinkStartResponse(BaseModel):
    code: str
    deep_link: str
    expires_at: datetime


# ── DB session dependency ─────────────────────────────────────────────────────

async def get_db(container: Container = Depends(get_container)):
    """Yield a raw AsyncSession from the container session factory."""
    async with container.session_factory() as session:
        yield session


# ── Auth dependency ───────────────────────────────────────────────────────────

async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> UserModel:
    settings = get_settings()
    token = request.cookies.get(settings.jwt_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = decode_access_token(token, settings.jwt_secret, settings.jwt_algorithm)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    result = await session.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


CurrentUser = Annotated[UserModel, Depends(get_current_user)]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Create a new user account and return a session cookie."""
    settings = get_settings()

    # Check email uniqueness
    existing_email = await session.execute(
        select(UserModel).where(UserModel.email == body.email)
    )
    if existing_email.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Check login uniqueness
    existing_login = await session.execute(
        select(UserModel).where(UserModel.login == body.login)
    )
    if existing_login.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Login already taken",
        )

    display_name = f"{body.first_name} {body.last_name}".strip()
    user = UserModel(
        id=uuid4(),
        email=body.email,
        login=body.login,
        password_hash=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        display_name=display_name,
        bio="",
        photo_data_url="",
        role="member",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info("New user registered: %s (%s)", user.email, user.id)

    _set_session_cookie(response, user.id, settings)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=UserResponse)
async def login(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Authenticate and set a session cookie."""
    settings = get_settings()

    result = await session.execute(
        select(UserModel).where(UserModel.email == body.email)
    )
    user = result.scalar_one_or_none()

    if (
        user is None
        or not user.password_hash
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    _set_session_cookie(response, user.id, settings)
    logger.info("User logged in: %s", user.email)
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateProfileRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update profile fields for the authenticated user."""
    if body.first_name is not None:
        current_user.first_name = body.first_name.strip()
    if body.last_name is not None:
        current_user.last_name = body.last_name.strip()
    if body.display_name is not None:
        current_user.display_name = body.display_name.strip()
    if body.bio is not None:
        current_user.bio = body.bio
    if body.photo_data_url is not None:
        current_user.photo_data_url = body.photo_data_url
    if body.role is not None:
        current_user.role = body.role.strip()

    # Auto-sync display_name from first+last if not explicitly set
    if body.display_name is None and (body.first_name or body.last_name):
        fn = current_user.first_name or ""
        ln = current_user.last_name or ""
        current_user.display_name = f"{fn} {ln}".strip()

    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.post("/telegram-link/start", response_model=TelegramLinkStartResponse)
async def start_telegram_link(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> TelegramLinkStartResponse:
    """Create a short one-time code for binding Telegram via bot deep-link."""
    settings = get_settings()
    now = datetime.now(UTC)
    existing = await session.execute(
        select(m.TelegramLinkCodeModel).where(
            m.TelegramLinkCodeModel.user_id == current_user.id,
            m.TelegramLinkCodeModel.used_at.is_(None),
        )
    )
    for row in existing.scalars():
        row.used_at = now

    code = await _unique_telegram_link_code(session)
    expires_at = now + timedelta(minutes=10)
    session.add(
        m.TelegramLinkCodeModel(
            id=uuid4(),
            user_id=current_user.id,
            code=code,
            expires_at=expires_at,
        )
    )
    await session.commit()
    username = settings.telegram_bot_username.strip().lstrip("@")
    return TelegramLinkStartResponse(
        code=code,
        deep_link=f"https://t.me/{username}?start=link_{code}",
        expires_at=expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Clear session cookie."""
    settings = get_settings()
    response.delete_cookie(
        key=settings.jwt_cookie_name,
        path="/",
        secure=settings.jwt_cookie_secure,
        httponly=True,
        samesite="lax",
    )


async def _unique_telegram_link_code(session: AsyncSession) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(10):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        existing = await session.execute(
            select(m.TelegramLinkCodeModel).where(m.TelegramLinkCodeModel.code == code)
        )
        if existing.scalar_one_or_none() is None:
            return code
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not generate link code")


# ── Cookie helper ─────────────────────────────────────────────────────────────

class TelegramWebAppAuthRequest(BaseModel):
    init_data: str


def _validate_webapp_init_data(init_data: str, bot_token: str) -> dict | None:
    """Проверка подписи Telegram Mini App initData (HMAC-SHA256). None — невалидно."""
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:  # noqa: BLE001
        return None
    received = pairs.pop("hash", None)
    if not received:
        return None
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        return None
    return pairs


@router.post("/telegram-webapp", response_model=UserResponse)
async def telegram_webapp_auth(
    body: TelegramWebAppAuthRequest,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Авто-вход из Telegram Mini App: валидируем initData → находим юзера по
    привязанному telegram_user_id → ставим сессию (кабинет открывается залогиненным)."""
    settings = get_settings()
    pairs = _validate_webapp_init_data(body.init_data, settings.telegram_bot_token)
    if pairs is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram WebApp signature")
    user_raw = pairs.get("user")
    if not user_raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No user in init data")
    try:
        tg_id = int(json.loads(user_raw).get("id"))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad user payload") from exc
    user = await session.scalar(select(UserModel).where(UserModel.telegram_user_id == tg_id))
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Telegram не привязан к аккаунту. Привяжите его в кабинете (Профиль).",
        )
    _set_session_cookie(response, user.id, settings)
    return UserResponse.model_validate(user)


def _set_session_cookie(response: Response, user_id: UUID, settings) -> None:
    token = create_access_token(
        user_id=user_id,
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expire_days=settings.jwt_expire_days,
    )
    response.set_cookie(
        key=settings.jwt_cookie_name,
        value=token,
        max_age=settings.jwt_expire_days * 86400,
        path="/",
        secure=settings.jwt_cookie_secure,
        httponly=True,
        samesite="lax",
    )
