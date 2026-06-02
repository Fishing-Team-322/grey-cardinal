# syntax=docker/dockerfile:1.7
# Образ audio-worker (P0 — каркас). Контекст сборки — корень монорепо.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1

WORKDIR /app

COPY packages/contracts/python /app/packages/contracts/python
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e /app/packages/contracts/python

COPY apps/audio-worker /app/apps/audio-worker
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e /app/apps/audio-worker

WORKDIR /app/apps/audio-worker
EXPOSE 8020

CMD ["uvicorn", "audio_worker.main:app", "--host", "0.0.0.0", "--port", "8020"]
