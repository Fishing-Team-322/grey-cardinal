from brain_api.main import create_app


def test_no_duplicate_ai_inbox_route_contract():
    app = create_app()
    matches = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/teams/{team_id}/ai-inbox"
        and "GET" in getattr(route, "methods", set())
    ]

    assert len(matches) == 1
