from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain_api.api.routes.health import router


def test_health() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "brain-api"}
