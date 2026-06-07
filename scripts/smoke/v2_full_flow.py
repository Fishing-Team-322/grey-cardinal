from __future__ import annotations

from datetime import UTC, datetime

from v2_smoke_lib import (
    V2SmokeClient,
    create_director_company,
    create_team,
    create_team_invite,
)


def main() -> None:
    stamp = int(datetime.now(UTC).timestamp() * 1000)
    employee_tg_id = stamp
    manager_tg_id = stamp + 1
    team_chat_id = -(stamp + 100_000)

    director = V2SmokeClient()
    _, company = create_director_company(director)
    team = create_team(director, company["id"], "Smoke Full Flow")
    manager_invite = create_team_invite(director, company["id"], team["id"], "manager")

    manager = V2SmokeClient()
    manager.register("manager-full", "Flow", "Manager")
    manager.request("POST", f"/api/invites/{manager_invite['token']}/accept")
    manager_link = manager.request("POST", "/api/users/me/telegram/link")
    manager.internal(
        "/internal/telegram/link",
        {
            "code": manager_link["code"],
            "tg_user_id": manager_tg_id,
            "chat_id": manager_tg_id,
            "username": "manager_flow",
            "first_name": "Flow",
            "last_name": "Manager",
        },
    )
    employee_invite = create_team_invite(manager, company["id"], team["id"], "employee")
    manager.request(
        "POST",
        f"/api/teams/{team['id']}/llm-settings",
        json={
            "provider": "local",
            "base_url": "http://ollama:11434/v1",
            "model": "qwen2.5:7b",
        },
    )
    board = manager.request("GET", f"/api/teams/{team['id']}/integrations/yougile/status")
    assert board["connected"] is False
    bind = manager.request("POST", f"/api/teams/{team['id']}/telegram/bind-code")
    manager.internal(
        "/internal/telegram/bind-team",
        {"code": bind["code"], "tg_chat_id": team_chat_id, "chat_id": team_chat_id},
    )

    employee = V2SmokeClient()
    employee.register("employee-full", "Flow", "Employee")
    employee.request("POST", f"/api/invites/{employee_invite['token']}/accept")
    employee_link = employee.request("POST", "/api/users/me/telegram/link")
    employee.internal(
        "/internal/telegram/link",
        {
            "code": employee_link["code"],
            "tg_user_id": employee_tg_id,
            "chat_id": employee_tg_id,
            "username": "employee_flow",
            "first_name": "Flow",
            "last_name": "Employee",
        },
    )

    actions = manager.internal(
        "/internal/telegram/message",
        {
            "update_id": stamp + 2,
            "message_id": stamp + 2,
            "chat": {
                "id": team_chat_id,
                "type": "supergroup",
                "title": "Smoke Full Flow",
            },
            "sender": {
                "id": employee_tg_id,
                "username": "employee_flow",
                "first_name": "Flow",
                "last_name": "Employee",
            },
            "text": "Employee, подготовь итоговый отчёт до завтра 18:00",
            "date": datetime.now(UTC).isoformat(),
        },
    )
    assert actions["actions"], "semantic message must produce a task proposal"
    keyboard = actions["actions"][0]["reply_markup"]["inline_keyboard"]
    confirm_data = keyboard[0][0]["callback_data"]
    manager.internal(
        "/internal/telegram/callback",
        {
            "update_id": stamp + 3,
            "callback_query_id": f"smoke-confirm-{stamp}",
            "from_user": {
                "id": manager_tg_id,
                "username": "manager_flow",
                "first_name": "Flow",
                "last_name": "Manager",
            },
            "message": {"message_id": stamp + 4, "chat_id": team_chat_id},
            "data": confirm_data,
        },
    )

    reports = manager.internal(
        "/internal/telegram/command",
        {
            "update_id": stamp + 5,
            "message_id": stamp + 5,
            "chat": {"id": team_chat_id, "type": "supergroup", "title": "Smoke Full Flow"},
            "sender": {
                "id": manager_tg_id,
                "username": "manager_flow",
                "first_name": "Flow",
                "last_name": "Manager",
            },
            "command": "reports",
            "args": [],
            "text": "/reports",
            "date": datetime.now(UTC).isoformat(),
        },
    )
    report_data = reports["actions"][0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    report = manager.internal(
        "/internal/telegram/callback",
        {
            "update_id": stamp + 6,
            "callback_query_id": f"smoke-report-{stamp}",
            "from_user": {
                "id": manager_tg_id,
                "username": "manager_flow",
                "first_name": "Flow",
                "last_name": "Manager",
            },
            "message": {"message_id": stamp + 6, "chat_id": team_chat_id},
            "data": report_data,
        },
    )
    report_text = "\n".join(action.get("text", "") for action in report["actions"])
    assert "Отчёт: Flow Employee" in report_text
    assert "Назначено: 1" in report_text

    overview = director.request("GET", f"/api/companies/{company['id']}/overview")
    assert overview["totals"]["teams"] >= 1
    assert overview["totals"]["open_tasks"] >= 1
    assert any(item["id"] == team["id"] for item in overview["teams"])
    print("[PASS] v2 full flow smoke")


if __name__ == "__main__":
    main()
