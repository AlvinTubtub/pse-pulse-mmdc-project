"""Tests for system readiness and public error redaction."""

from backend.app.database import get_db


def test_system_status_endpoint(client):
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["database"] == "connected"
    assert data["demo_mode"] is True
    assert "memory" not in data
    assert "deployment_target" not in data


def test_system_status_suppresses_database_exception(client):
    from backend.app.main import app

    class BrokenSession:
        def execute(self, statement):
            raise RuntimeError("secret-password and /private/path must stay private")

    def broken_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    try:
        response = client.get("/api/v1/system/status")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    assert response.json()["database"] == "unavailable"
    assert response.json()["status"] == "degraded"
    assert "secret-password" not in response.text
    assert "/private/path" not in response.text
