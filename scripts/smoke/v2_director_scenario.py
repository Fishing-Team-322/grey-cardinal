from __future__ import annotations

from v2_smoke_lib import V2SmokeClient, create_director_company, create_team


def main() -> None:
    client = V2SmokeClient()
    _, company = create_director_company(client)
    team_a = create_team(client, company["id"], "Smoke Backend")
    team_b = create_team(client, company["id"], "Smoke Ops")
    overview = client.request("GET", f"/api/companies/{company['id']}/overview")

    assert overview["totals"]["teams"] >= 2
    assert {team["id"] for team in overview["teams"]} >= {team_a["id"], team_b["id"]}
    print("[PASS] v2 director scenario")


if __name__ == "__main__":
    main()
