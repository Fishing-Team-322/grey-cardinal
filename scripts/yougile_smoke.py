from __future__ import annotations

import json
import os
import sys

import httpx


def _env(name: str, *, required: bool = True) -> str:
    value = os.getenv(name, "").strip()
    if required and not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> None:
    if os.getenv("YOUGILE_SMOKE_CONFIRM") != "1":
        raise SystemExit(
            "Smoke создаёт реальную тестовую карточку. Повторите с YOUGILE_SMOKE_CONFIRM=1."
        )
    base = _env("YOUGILE_API_BASE_URL", required=False) or "https://ru.yougile.com"
    api_key = _env("YOUGILE_API_KEY")
    todo = _env("YOUGILE_COLUMN_TODO_ID")
    in_progress = _env("YOUGILE_COLUMN_IN_PROGRESS_ID")
    done = _env("YOUGILE_COLUMN_DONE_ID")
    headers = {"Authorization": f"Bearer {api_key}"}
    root = base.rstrip("/") + "/api-v2"

    with httpx.Client(timeout=20, headers=headers) as client:
        created = client.post(
            f"{root}/tasks",
            json={"title": "[Grey Cardinal smoke] test card", "columnId": todo},
        )
        created.raise_for_status()
        task_id = created.json()["id"]
        client.put(f"{root}/tasks/{task_id}", json={"columnId": in_progress}).raise_for_status()
        comment = client.post(
            f"{root}/tasks/{task_id}/chat-messages",
            json={"text": "Grey Cardinal integration smoke"},
        )
        client.put(
            f"{root}/tasks/{task_id}",
            json={"columnId": done, "completed": True},
        ).raise_for_status()

    json.dump(
        {
            "ok": True,
            "task_id": task_id,
            "comment_status": comment.status_code,
            "final_state": "done",
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    print()


if __name__ == "__main__":
    main()
