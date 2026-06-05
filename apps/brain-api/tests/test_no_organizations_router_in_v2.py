"""Item 2: в production app не должно быть старого organizations-роутера.

v2 использует единую Company/Team модель; параллельная Organization-модель не
маунтится, чтобы не было двух способов создать «организацию».
"""

from brain_api.main import create_app


def test_no_api_organizations_routes_mounted():
    app = create_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not any(p.startswith("/api/organizations") for p in paths), (
        "organizations.router не должен быть подключён в production app"
    )


def test_v2_company_team_routes_present():
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/companies" in paths
    assert "/api/companies/{company_id}/teams" in paths
