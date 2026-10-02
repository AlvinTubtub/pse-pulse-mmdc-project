"""Tests for forecast endpoints."""

def test_get_latest_forecasts(client):
    response = client.get("/api/v1/forecasts/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["is_demo"] is True
    assert "DEMO DATA" in data["disclaimer"]
    assert "forecasts" in data
    assert len(data["forecasts"]) > 0

    first = data["forecasts"][0]
    assert "symbol" in first
    assert "model_name" in first
    assert "model_code" in first
    assert "predicted_price" in first
    assert "target_date" in first
    assert first["is_demo"] is True
    assert first["pipeline_run_id"] is not None


def test_forecasts_symbol_filter(client):
    response = client.get("/api/v1/forecasts/latest?symbol=BDO")
    assert response.status_code == 200
    data = response.json()
    assert len(data["forecasts"]) > 0
    for f in data["forecasts"]:
        assert f["symbol"] == "BDO"


def test_forecasts_model_code_filter(client):
    response = client.get("/api/v1/forecasts/latest?model_code=LAG_REGRESSION")
    assert response.status_code == 200
    data = response.json()
    assert len(data["forecasts"]) > 0
    for f in data["forecasts"]:
        assert f["model_code"] == "LAG_REGRESSION"


def test_model_multi_version_coexistence(db_session):
    """Verify that multiple versions of the same model code can coexist."""
    from backend.app.models.model_metadata import ModelMetadata
    import pytest
    from sqlalchemy.exc import IntegrityError

    # BASELINE_SMA v1.0.0 exists in seed data. Adding v2.0.0 should succeed.
    v2 = ModelMetadata(
        name="Baseline SMA 5-Day v2",
        code="BASELINE_SMA",
        version="v2.0.0",
        description="Updated baseline version",
        is_active=False,
    )
    db_session.add(v2)
    db_session.commit()
    assert v2.id is not None

    # Adding duplicate (code, version) should raise IntegrityError
    dup = ModelMetadata(
        name="Duplicate SMA",
        code="BASELINE_SMA",
        version="v2.0.0",
        description="Duplicate",
        is_active=False,
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
