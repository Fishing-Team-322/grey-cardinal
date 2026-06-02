# Grey Cardinal — команды для разработки.
# На Windows используйте `make` из Git Bash / WSL, либо запускайте команды вручную
# (см. README.md, раздел «Запуск без make»).

.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install dev test lint format migrate \
        docker-up docker-down docker-build brain bot audio frontend set-telegram-webhook

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

install: ## Установить все Python-зависимости (editable) для локальной разработки
	$(PY) -m pip install -e packages/contracts/python
	$(PY) -m pip install -e "apps/brain-api[dev]"
	$(PY) -m pip install -e "apps/telegram-bot[dev]"
	$(PY) -m pip install -e "apps/audio-worker[dev]"

dev: ## Поднять базовый профиль (postgres + brain-api + telegram-bot)
	docker compose up postgres brain-api telegram-bot

test: ## Прогнать все тесты (pytest)
	$(PY) -m pytest

lint: ## Проверить код ruff + mypy
	$(PY) -m ruff check .
	$(PY) -m mypy apps/brain-api/src apps/telegram-bot/src packages/contracts/python/grey_cardinal_contracts

format: ## Отформатировать код ruff
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

migrate: ## Применить миграции brain-api (внутри контейнера)
	docker compose exec brain-api alembic upgrade head

docker-up: ## Поднять полный профиль в фоне
	docker compose --profile full up -d --build

docker-down: ## Остановить и удалить контейнеры
	docker compose --profile full down

docker-build: ## Пересобрать образы (с кешем)
	docker compose --profile full build

brain: ## Запустить brain-api локально (uvicorn)
	cd apps/brain-api && $(PY) -m uvicorn brain_api.main:app --host 0.0.0.0 --port 8000 --reload

bot: ## Запустить telegram-bot локально (uvicorn)
	cd apps/telegram-bot && $(PY) -m uvicorn telegram_bot.main:app --host 0.0.0.0 --port 8010 --reload

audio: ## Запустить audio-worker локально (uvicorn)
	cd apps/audio-worker && $(PY) -m uvicorn audio_worker.main:app --host 0.0.0.0 --port 8020 --reload

frontend: ## Запустить frontend-dashboard локально (vite)
	cd apps/frontend-dashboard && npm install && npm run dev

set-telegram-webhook: ## Зарегистрировать Telegram webhook (нужны TELEGRAM_BOT_TOKEN и TELEGRAM_PUBLIC_BASE_URL)
	curl -sS -X POST "https://api.telegram.org/bot$${TELEGRAM_BOT_TOKEN}/setWebhook" \
		-d "url=$${TELEGRAM_PUBLIC_BASE_URL}/webhooks/telegram" \
		-d "secret_token=$${TELEGRAM_WEBHOOK_SECRET}" \
		-d "allowed_updates=[\"message\",\"callback_query\"]"
