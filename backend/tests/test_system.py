"""Tests for system status endpoint."""

def test_system_status_endpoint(client):
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["operational", "degraded"]
    assert "environment" in data
    assert "database" in data
    assert data["database"]["status"] == "connected"
    assert "memory" in data
    assert data["memory"]["target_host_ram_mb"] == 1024
    assert data["demo_mode"] is True
    assert "deployment_target" in data
    assert "B2ats_v2" in data["deployment_target"]["primary_vm_sku"]
