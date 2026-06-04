"""Точка входа brain-api (FastAPI)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from brain_api.api.routes import (
    agents,
    debug,
    desktop,
    health,
    internal_audio,
    internal_telegram,
    meetings,
    public_api,
    tasks,
    telemost,
    websocket,
)
from brain_api.config import get_settings
from brain_api.container import Container
from brain_api.demo import routes as demo_routes
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
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=[
            "Content-Type",
            "X-Internal-Token",
            "X-GC-User-Id",
            "X-GC-Device-Id",
            "X-GC-Client-Session-Id",
        ],
    )
    app.include_router(health.router)
    app.include_router(public_api.router)
    app.include_router(agents.router)
    app.include_router(telemost.router)
    app.include_router(demo_routes.router)
    app.include_router(debug.router)
    app.include_router(desktop.router)
    app.include_router(internal_telegram.router)
    app.include_router(internal_audio.router)
    app.include_router(meetings.router)
    app.include_router(tasks.router)
    app.include_router(websocket.router)
    return app


app = create_app()
