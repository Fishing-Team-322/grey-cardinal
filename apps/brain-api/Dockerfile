# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1

WORKDIR /app

COPY packages/contracts/python /app/packages/contracts/python
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e /app/packages/contracts/python

COPY apps/brain-api /app/apps/brain-api
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e /app/apps/brain-api

WORKDIR /app/apps/brain-api
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn brain_api.main:app --host 0.0.0.0 --port 8000"]
