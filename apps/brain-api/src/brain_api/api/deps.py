"""Зависимости FastAPI: доступ к контейнеру и проверка internal-токена."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from brain_api.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


async def verify_internal_token(
    request: Request,
    x_internal_token: str | None = Header(default=None),
) -> None:
    expected = request.app.state.container.settings.internal_api_token
    if not x_internal_token or x_internal_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-Token",
        )
