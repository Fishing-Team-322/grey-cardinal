from __future__ import annotations

import argparse
import json
import os
import sys
from urllib import parse, request

COMMANDS = [
    ("start", "Подключить Серого кардинала"),
    ("help", "Показать команды"),
    ("tasks", "Активные задачи"),
    ("tasks_all", "Все активные задачи workspace"),
    ("start_task", "Взять задачу в работу"),
    ("block", "Заблокировать задачу"),
    ("done", "Закрыть задачу"),
    ("digest", "Показать дайджест"),
    ("demo_start", "Запустить демо-сценарий"),
    ("demo_reset", "Очистить demo-данные"),
    ("demo_transcript", "Добавить demo-реплику"),
    ("meeting_start", "Начать встречу"),
    ("meeting_stop", "Завершить встречу"),
    ("meeting_status", "Статус встречи"),
    ("bind_chat", "Привязать чат к workspace"),
]


def _token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    return token


def _call(method: str, payload: dict | None = None) -> dict:
    data = parse.urlencode(payload or {}).encode()
    req = request.Request(
        f"https://api.telegram.org/bot{_token()}/{method}",
        data=data if payload is not None else None,
        method="POST" if payload is not None else "GET",
    )
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read())


def set_webhook() -> dict:
    base_url = os.getenv("TELEGRAM_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        raise SystemExit("TELEGRAM_PUBLIC_BASE_URL is required")
    payload = {
        "url": f"{base_url}/webhooks/telegram",
        "allowed_updates": json.dumps(["message", "callback_query"]),
    }
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if secret:
        payload["secret_token"] = secret
    return _call("setWebhook", payload)


def webhook_info() -> dict:
    response = _call("getWebhookInfo")
    result = response.get("result", {})
    return {
        "ok": response.get("ok", False),
        "url": result.get("url", ""),
        "pending_update_count": result.get("pending_update_count", 0),
        "last_error_message": result.get("last_error_message"),
        "allowed_updates": result.get("allowed_updates", []),
    }


def set_commands() -> dict:
    return _call(
        "setMyCommands",
        {
            "commands": json.dumps(
                [{"command": name, "description": text} for name, text in COMMANDS]
            )
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["set-webhook", "webhook-info", "set-commands"])
    args = parser.parse_args()
    result = {
        "set-webhook": set_webhook,
        "webhook-info": webhook_info,
        "set-commands": set_commands,
    }[args.action]()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
