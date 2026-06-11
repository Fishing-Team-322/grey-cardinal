from brain_api.api.routes.health import _alembic_heads


def test_readiness_uses_current_alembic_head() -> None:
    assert _alembic_heads() == {"0017_team_pet_full"}
