# syntax=docker/dockerfile:1.7
# Образ frontend-dashboard (P0 — каркас). Контекст сборки — сама папка приложения.
# Для P0 запускаем dev-сервер Vite. BuildKit cache-mount ускоряет npm install.

FROM node:20-alpine AS base

WORKDIR /app

# Сначала только манифесты — слой кешируется, пока не меняются зависимости.
COPY package.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install

# Затем исходники.
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
