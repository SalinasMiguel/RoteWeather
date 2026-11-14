"""PLAN §1 — Test baseline health endpoint."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_T0_1_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
