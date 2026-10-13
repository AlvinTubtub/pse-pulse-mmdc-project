"""Tests for health and root endpoints."""

def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "project" in data
    assert data["project"] == "PSE Pulse — Personal Azure Edition"
    assert "version" in data
    assert "docs" not in data


def test_health_check_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data


def test_liveness_and_readiness_are_distinct(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_readiness_failure_is_generic_and_liveness_stays_up(client, monkeypatch):
    from backend.app import main

    class BrokenEngine:
        def connect(self):
            raise RuntimeError("password=do-not-return; private-host.internal")

    monkeypatch.setattr(main, "engine", BrokenEngine())
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.json() == {"status": "not_ready", "reason": "dependency_unavailable"}
    assert "do-not-return" not in ready.text
    assert "private-host.internal" not in ready.text
