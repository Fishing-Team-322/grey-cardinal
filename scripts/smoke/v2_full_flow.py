from __future__ import annotations

from v2_smoke_lib import (
    V2SmokeClient,
    create_director_company,
    create_team,
    create_team_invite,
)


def main() -> None:
    director = V2SmokeClient()
    _, company = create_director_company(director)
    team = create_team(director, company["id"], "Smoke Full Flow")
    manager_invite = create_team_invite(director, company["id"], team["id"], "manager")
    employee_invite = create_team_invite(director, company["id"], team["id"], "employee")

    manager = V2SmokeClient()
    manager.register("manager-full", "Flow", "Manager")
    manager.request("POST", f"/api/invites/{manager_invite['token']}/accept")
    manager.request(
        "POST",
        f"/api/teams/{team['id']}/llm-settings",
        json={
            "provider": "local",
            "base_url": "http://ollama:11434/v1",
            "model": "qwen2.5:7b",
        },
    )
    manager.request(
        "POST",
        f"/api/teams/{team['id']}/board",
        json={
            "provider": "yougile",
            "credentials": {"api_key": "smoke-key"},
            "config": {"project_id": "smoke", "board_id": "smoke", "column_todo_id": "todo"},
        },
    )
    bind = manager.request("POST", f"/api/teams/{team['id']}/telegram/bind-code")
    manager.internal(
        "/internal/telegram/bind-team",
        {"code": bind["code"], "tg_chat_id": -100400500, "chat_id": -100400500},
    )

    employee = V2SmokeClient()
    employee.register("employee-full", "Flow", "Employee")
    employee.request("POST", f"/api/invites/{employee_invite['token']}/accept")
    employee.request("POST", "/api/users/me/telegram/link")

    overview = director.request("GET", f"/api/companies/{company['id']}/overview")
    assert overview["totals"]["teams"] >= 1
    assert any(item["id"] == team["id"] for item in overview["teams"])
    print("[PASS] v2 full flow smoke")


if __name__ == "__main__":
    main()
