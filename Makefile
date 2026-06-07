.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install dev test test-all lint format migrate docker-up docker-down docker-build \
        brain bot audio frontend set-telegram-webhook get-telegram-webhook-info \
        set-telegram-commands test-agent audio-agent-configure check-frontend-downloads \
        audio-agent-build audio-agent-test audio-agent-run audio-worker-test-chunk \
        smoke-desktop-flow smoke-alembic-fresh-db smoke-v2-director \
        smoke-v2-manager smoke-v2-employee smoke-v2-full

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

install: ## Установить editable Python-зависимости для разработки
	$(PY) -m pip install -e packages/contracts/python
	$(PY) -m pip install -e "apps/brain-api[dev]"
	$(PY) -m pip install -e "apps/telegram-bot[dev]"
	$(PY) -m pip install -e "apps/audio-worker[dev]"

dev: ## Поднять postgres, brain-api и telegram-bot
	docker compose up postgres brain-api telegram-bot

test: ## Прогнать Python-тесты
	$(PY) -m pytest

test-all: test test-agent ## Прогнать Python и native agent тесты

lint: ## Проверить Python-код ruff и mypy
	$(PY) -m ruff check .
	$(PY) -m mypy apps/brain-api/src apps/telegram-bot/src packages/contracts/python/grey_cardinal_contracts

format: ## Отформатировать Python-код
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

migrate: ## Применить Alembic-миграции внутри brain-api
	docker compose exec brain-api alembic upgrade head

docker-up: ## Поднять полный Docker-профиль в фоне
	docker compose --profile full up -d --build

docker-down: ## Остановить Docker-сервисы
	docker compose --profile full down

check-frontend-downloads: ## Проверить, что MSI трей-агента на месте перед сборкой фронта
	bash scripts/check_frontend_downloads.sh

docker-build: check-frontend-downloads ## Собрать Docker-образы
	docker compose --profile full build

brain: ## Запустить brain-api локально
	cd apps/brain-api && $(PY) -m uvicorn brain_api.main:app --host 0.0.0.0 --port 8000 --reload

bot: ## Запустить telegram-bot локально
	cd apps/telegram-bot && $(PY) -m uvicorn telegram_bot.main:app --host 0.0.0.0 --port 8010 --reload

audio: ## Запустить audio-worker локально
	cd apps/audio-worker && $(PY) -m uvicorn audio_worker.main:app --host 0.0.0.0 --port 8020 --reload

frontend: ## Запустить frontend-dashboard локально
	cd apps/frontend && npm install && npm run dev

set-telegram-webhook: ## Зарегистрировать Telegram webhook
	$(PY) scripts/telegram_setup.py set-webhook

get-telegram-webhook-info: ## Показать текущую конфигурацию Telegram webhook
	$(PY) scripts/telegram_setup.py webhook-info

set-telegram-commands: ## Зарегистрировать список Telegram-команд
	$(PY) scripts/telegram_setup.py set-commands

smoke-desktop-flow: ## Проверить desktop-first microphone flow через brain-api
	$(PY) scripts/smoke/desktop_microphone_flow.py

smoke-alembic-fresh-db: ## Проверить Alembic на пустой PostgreSQL DB
	$(PY) scripts/smoke/alembic_fresh_db_check.py

smoke-v2-director: ## Smoke v2 director scenario через HTTP API
	$(PY) scripts/smoke/v2_director_scenario.py

smoke-v2-manager: ## Smoke v2 manager scenario через HTTP API
	$(PY) scripts/smoke/v2_manager_scenario.py

smoke-v2-employee: ## Smoke v2 employee scenario через HTTP API
	$(PY) scripts/smoke/v2_employee_scenario.py

smoke-v2-full: ## Smoke полный v2 flow через HTTP API
	$(PY) scripts/smoke/v2_full_flow.py

test-agent: audio-agent-configure audio-agent-build audio-agent-test ## Собрать и протестировать native audio-agent

audio-agent-configure: ## Сконфигурировать native audio-agent
	cd native/desktop-agent && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release

audio-agent-build: ## Собрать native audio-agent
	cd native/desktop-agent && cmake --build build --config Release

audio-agent-test: ## Прогнать native audio-agent тесты
	cd native/desktop-agent && ctest --test-dir build --output-on-failure -C Release

audio-agent-run: ## Запустить Windows native audio-agent
	powershell -NoProfile -ExecutionPolicy Bypass -Command "& '.\native\desktop-agent\build\Release\grey-cardinal-agent.exe' --server http://localhost:8020 --token dev-internal-token --meeting-id demo-meeting"

audio-worker-test-chunk: ## Отправить mock WAV в audio-worker
	powershell -NoProfile -ExecutionPolicy Bypass -File .\apps\audio-worker\scripts\send_mock_wav.ps1 -Server http://localhost:8020 -Token dev-internal-token -MeetingId demo-meeting
