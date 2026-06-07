from brain_api.main import create_app


def test_no_duplicate_grey_board_route_contract():
    app = create_app()
    matches = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/teams/{team_id}/grey-board"
        and "GET" in getattr(route, "methods", set())
    ]

    assert len(matches) == 1
