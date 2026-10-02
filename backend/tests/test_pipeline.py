"""Tests for pipeline endpoints and validation/feature components."""

from datetime import date
from backend.pipeline.validation.data_validator import DataValidator
from backend.pipeline.features.feature_builder import FeatureBuilder


def test_pipeline_status_endpoint(client):
    response = client.get("/api/v1/pipeline/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["idle", "active"]
    assert "schedule" in data
    assert data["is_demo_mode"] is True
    assert "stages" in data
    assert "ingest" in data["stages"]
    assert "forecasting" in data["stages"]
    assert data["last_run"] is not None
    assert data["last_run"]["is_demo_run"] is True


def test_data_validator_valid():
    record = {
        "open_price": 100.0,
        "high_price": 105.0,
        "low_price": 98.0,
        "close_price": 102.0,
        "volume": 50000,
    }
    is_valid, errors = DataValidator.validate_ohlc_record(record)
    assert is_valid is True
    assert len(errors) == 0


def test_data_validator_invalid_high_low():
    record = {
        "open_price": 100.0,
        "high_price": 95.0,  # Invalid: high is lower than open
        "low_price": 98.0,
        "close_price": 102.0,
        "volume": 50000,
    }
    is_valid, errors = DataValidator.validate_ohlc_record(record)
    assert is_valid is False
    assert len(errors) > 0


def test_data_validator_negative_volume():
    record = {
        "open_price": 100.0,
        "high_price": 105.0,
        "low_price": 98.0,
        "close_price": 102.0,
        "volume": -10,  # Invalid
    }
    is_valid, errors = DataValidator.validate_ohlc_record(record)
    assert is_valid is False
    assert any("volume" in e.lower() for e in errors)


def test_feature_builder():
    prices = [10.0, 10.5, 11.0, 10.8, 11.2, 11.5]
    feats = FeatureBuilder.extract_lag_features(prices, lags=[1, 2, 5])
    assert "lag_1" in feats
    assert feats["lag_1"] == 11.2
    assert "ma_5" in feats
    assert feats["ma_5"] > 0
