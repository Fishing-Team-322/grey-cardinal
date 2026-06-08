# syntax=docker/dockerfile:1.7
# Образ telegram-bot. Контекст сборки — корень монорепо.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel

COPY packages/contracts/python /app/packages/contracts/python
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-build-isolation -e /app/packages/contracts/python

COPY apps/telegram-bot /app/apps/telegram-bot
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-build-isolation -e /app/apps/telegram-bot

WORKDIR /app/apps/telegram-bot
EXPOSE 8010

CMD ["uvicorn", "telegram_bot.main:app", "--host", "0.0.0.0", "--port", "8010"]
