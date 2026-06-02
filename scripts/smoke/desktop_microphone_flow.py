from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request_json(
    method: str,
    base_url: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
    identity: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Token": token,
    }
    if identity:
        headers.update(
            {
                "X-GC-User-Id": identity["user_id"],
                "X-GC-Device-Id": identity["device_id"],
                "X-GC-Client-Session-Id": identity["client_session_id"],
            }
        )
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8010")
    parser.add_argument("--token", default="dev-internal-token")
    parser.add_argument("--meeting-id", default="MTG-1")
    args = parser.parse_args()

    print("[smoke] register device for Petya")
    identity = request_json(
        "POST",
        args.base_url,
        "/desktop/devices/register",
        args.token,
        {
            "display_name": "Петя",
            "telegram_username": "petya",
            "device_name": "Petya Laptop",
            "platform": "windows",
            "app_version": "0.1.0",
        },
    )

    print("[smoke] join meeting")
    request_json(
        "POST",
        args.base_url,
        f"/desktop/meetings/{args.meeting_id}/join",
        args.token,
        {},
        identity,
    )

    print("[smoke] send authenticated microphone transcript")
    transcript = request_json(
        "POST",
        args.base_url,
        "/desktop/transcripts",
        args.token,
        {
            "meeting_id": args.meeting_id,
            "text": "Я подготовлю оплату до завтра 18:00",
            "is_final": True,
            "microphone_id": "smoke_mock_microphone",
            "capture_mode": "microphone",
            "asr_provider": "mock",
            "asr_confidence": 0.91,
            "vad_confidence": 0.88,
            "duration_ms": 3200,
        },
        identity,
    )
    assert transcript["trusted_speaker"] is True
    assert transcript["proposal_created"] is True
    confirmation_id = transcript.get("confirmation_id")
    if not confirmation_id:
        raise RuntimeError("desktop transcript response did not include confirmation_id")

    print("[smoke] confirm proposal")
    request_json(
        "POST",
        args.base_url,
        "/internal/telegram/callback",
        args.token,
        {
            "update_id": 1,
            "callback_query_id": "smoke-confirm",
            "from_user": {"id": 1001, "username": "petya", "first_name": "Петя"},
            "message": {"message_id": 2001, "chat_id": -100123456789},
            "data": f"confirm_task:{confirmation_id}",
        },
    )

    print("[smoke] verify desktop task assignment")
    tasks = request_json("GET", args.base_url, "/desktop/tasks", args.token, identity=identity)
    task_items = tasks.get("tasks", [])
    if not task_items:
        raise RuntimeError("desktop task list is empty after confirmation")
    task = task_items[0]
    if task.get("assignee_text") != "Петя":
        raise RuntimeError(f"expected task assignee Petya, got {task.get('assignee_text')}")

    print("[smoke] mark task done")
    request_json(
        "POST",
        args.base_url,
        "/internal/telegram/command",
        args.token,
        {
            "update_id": 2,
            "message_id": 2002,
            "chat": {"id": -100123456789, "type": "supergroup", "title": "Smoke"},
            "sender": {"id": 1001, "username": "petya", "first_name": "Петя"},
            "command": "done",
            "args": [task["public_id"]],
            "text": f"/done {task['public_id']}",
            "date": "2026-06-02T15:10:00+03:00",
        },
    )

    print("[smoke] verify XP")
    xp = request_json(
        "GET", args.base_url, "/desktop/gamification/me", args.token, identity=identity
    )
    if xp["points_total"] < 40:
        raise RuntimeError(f"expected at least 40 XP, got {xp['points_total']}")

    print("[PASS] desktop microphone flow smoke passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
