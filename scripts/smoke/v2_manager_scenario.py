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
    team = create_team(director, company["id"], "Smoke Managers")
    invite = create_team_invite(director, company["id"], team["id"], "manager")

    manager = V2SmokeClient()
    manager.register("manager", "Smoke", "Manager")
    manager.request("POST", f"/api/invites/{invite['token']}/accept")

    manager.request(
        "POST",
        f"/api/teams/{team['id']}/llm-settings",
        json={
            "provider": "local",
            "base_url": "http://ollama:11434/v1",
            "model": "qwen2.5:7b",
        },
    )
    llm_health = manager.request("GET", f"/api/teams/{team['id']}/llm/health")
    assert llm_health["status"] in {"ok", "error"}

    manager.request(
        "POST",
        f"/api/teams/{team['id']}/board",
        json={
            "provider": "yougile",
            "credentials": {"api_key": "smoke-key"},
            "config": {"project_id": "smoke", "board_id": "smoke", "column_todo_id": "todo"},
        },
    )
    board_status = manager.request("GET", f"/api/teams/{team['id']}/board/status")
    assert board_status["configured"] is True

    bind = manager.request("POST", f"/api/teams/{team['id']}/telegram/bind-code")
    manager.internal(
        "/internal/telegram/bind-team",
        {"code": bind["code"], "tg_chat_id": -100200300, "chat_id": -100200300},
    )
    tg_status = manager.request("GET", f"/api/teams/{team['id']}/telegram/status")
    assert tg_status["linked"] is True
    print("[PASS] v2 manager scenario")


if __name__ == "__main__":
    main()
