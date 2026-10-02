"""Tests for forecasting provider interfaces and stubs."""

from datetime import date
from backend.app.forecasting.base import PriceHistoryItem
from backend.app.forecasting.providers.lag_regression import LagInformedRegressionProvider
from backend.app.forecasting.providers.arima import ArimaProvider
from backend.app.forecasting.providers.lstm import LstmProvider
from backend.app.forecasting.registry import forecast_registry


def _mock_history():
    return [
        PriceHistoryItem(
            trade_date=date(2026, 9, 15 + i),
            open_price=100.0 + i,
            high_price=105.0 + i,
            low_price=98.0 + i,
            close_price=102.0 + i,
            volume=50000,
        )
        for i in range(10)
    ]


def test_lag_regression_provider():
    provider = LagInformedRegressionProvider()
    assert provider.spec.code == "LAG_REGRESSION"
    assert provider.spec.is_stub is True

    history = _mock_history()
    forecasts = provider.generate_forecast("TEST", history, horizon_days=5)
    assert len(forecasts) == 5
    for pt in forecasts:
        assert pt.predicted_price > 0
        assert pt.is_demo is True
        assert pt.lower_bound <= pt.predicted_price <= pt.upper_bound


def test_arima_provider():
    provider = ArimaProvider()
    assert provider.spec.code == "ARIMA"
    assert provider.spec.is_stub is True

    history = _mock_history()
    forecasts = provider.generate_forecast("TEST", history, horizon_days=5)
    assert len(forecasts) == 5
    for pt in forecasts:
        assert pt.predicted_price > 0
        assert pt.is_demo is True
        assert pt.lower_bound <= pt.predicted_price <= pt.upper_bound


def test_lstm_provider():
    provider = LstmProvider()
    assert provider.spec.code == "LSTM"
    assert provider.spec.is_stub is True

    history = _mock_history()
    forecasts = provider.generate_forecast("TEST", history, horizon_days=5)
    assert len(forecasts) == 5
    for pt in forecasts:
        assert pt.predicted_price > 0
        assert pt.is_demo is True
        assert pt.lower_bound <= pt.predicted_price <= pt.upper_bound


def test_forecast_registry():
    assert forecast_registry.get("LAG_REGRESSION") is not None
    assert forecast_registry.get("ARIMA") is not None
    assert forecast_registry.get("LSTM") is not None
    assert forecast_registry.get("NONEXISTENT") is None
    all_providers = forecast_registry.list_all()
    assert len(all_providers) >= 3
