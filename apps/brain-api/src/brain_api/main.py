"""Точка входа brain-api (FastAPI)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from brain_api.api.routes import (
    accounts,
    agentic_pm,
    agents,
    daemon,
    debug,
    grey_board,
    health,
    internal_audio,
    internal_telegram,
    meetings,
    tasks,
    v2_tenants,
    websocket,
    yandex_telemost,
    yougile,
    yougile_board,
    yougile_webhooks,
)
from brain_api.config import get_settings
from brain_api.container import Container
from brain_api.infrastructure.logging.setup import setup_logging
from brain_api.infrastructure.scheduler.jobs import register_jobs
from brain_api.infrastructure.scheduler.runner import AsyncScheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("Starting brain-api (env=%s)", settings.app_env)

    container = Container(settings)
    app.state.container = container

    scheduler = AsyncScheduler(timezone=settings.default_timezone)
    register_jobs(scheduler, container)
    app.state.scheduler = scheduler
    logger.info("Scheduler started (reminders + digest)")

    try:
        yield
    finally:
        await scheduler.stop()
        await container.dispose()
        logger.info("brain-api stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Grey Cardinal - brain-api", version="0.1.0", lifespan=lifespan)
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=[
            "Content-Type",
            "X-Internal-Token",
        ],
    )
    app.include_router(health.router)
    app.include_router(accounts.router)
    app.include_router(agentic_pm.router)
    app.include_router(agents.router)
    app.include_router(daemon.router)
    app.include_router(debug.router)
    app.include_router(grey_board.router)
    app.include_router(internal_telegram.router)
    app.include_router(internal_audio.router)
    app.include_router(meetings.router)
    app.include_router(tasks.router)
    app.include_router(v2_tenants.router)
    app.include_router(websocket.router)
    app.include_router(yandex_telemost.router)
    app.include_router(yougile.router)
    app.include_router(yougile_board.router)
    app.include_router(yougile_board.sync_router)
    app.include_router(yougile_webhooks.router)
    return app


app = create_app()
