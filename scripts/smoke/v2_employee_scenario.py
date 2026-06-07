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
    team = create_team(director, company["id"], "Smoke Employees")
    invite = create_team_invite(director, company["id"], team["id"], "employee")

    employee = V2SmokeClient()
    employee.register("employee", "Smoke", "Employee")
    employee.request("POST", f"/api/invites/{invite['token']}/accept")
    link = employee.request("POST", "/api/users/me/telegram/link")
    assert link["deep_link"].startswith("https://t.me/")
    status = employee.request("GET", "/api/users/me/telegram/status")
    assert status["linked"] is False
    print("[PASS] v2 employee scenario")


if __name__ == "__main__":
    main()
