# syntax=docker/dockerfile:1.7
# Образ brain-api. Контекст сборки — корень монорепо (см. docker-compose.yml).
# Используются BuildKit cache-mount'ы: повторные сборки переиспользуют кеш pip.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1

WORKDIR /app

# 1) Общие контракты (меняются редко) — отдельный слой для кеша.
COPY packages/contracts/python /app/packages/contracts/python
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e /app/packages/contracts/python

# 2) brain-api: исходники + установка зависимостей (кеш pip переиспользуется).
COPY apps/brain-api /app/apps/brain-api
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e /app/apps/brain-api

WORKDIR /app/apps/brain-api
EXPOSE 8000

# Применяем миграции и запускаем API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn brain_api.main:app --host 0.0.0.0 --port 8000"]
