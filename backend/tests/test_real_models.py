"""Unit tests for Lag-Informed Regression and ARIMA real models."""

from datetime import date, timedelta
import numpy as np
import pytest

from backend.app.forecasting.real.config import (
    DEFAULT_ARIMA_CONFIG,
    DEFAULT_LAG_REGRESSION_CONFIG,
    ArimaConfig,
    LagRegressionConfig,
)
from backend.app.forecasting.real.domain import OhlcvRecord, build_next_day_pairs
from backend.app.forecasting.real.features.regression_features import build_regression_dataset
from backend.app.forecasting.real.models.arima import ArimaSpecification, fit_arima
from backend.app.forecasting.real.models.lag_regression import LagRegressionModel
from backend.app.forecasting.real.models.base import reconstruct_close
from backend.app.forecasting.real.training.cross_validation import select_pacf_lags
from backend.app.forecasting.real.training.refit_arima import refit_arima_for_production
from backend.app.forecasting.real.training.refit_lir import refit_lir_for_production


def test_lir_uses_absolute_close_delta_and_additive_reconstruction():
    """Lock the official target and prediction contract to arithmetic examples."""
    origin = OhlcvRecord(date(2026, 10, 1), 99.0, 104.0, 98.0, 100.0, 1000.0)
    target = OhlcvRecord(date(2026, 10, 2), 100.0, 104.0, 99.0, 103.0, 1100.0)

    pair = build_next_day_pairs([origin, target])[0]
    assert pair.target_delta == 3.0

    predicted_close = reconstruct_close(100.0, 2.5)
    assert float(predicted_close) == 102.5
    assert float(predicted_close) != 100.0 * (1.0 + 2.5)


def _generate_synthetic_series(n: int = 120, start_price: float = 100.0) -> list[OhlcvRecord]:
    """Generate trending synthetic OHLCV sequence."""
    records: list[OhlcvRecord] = []
    curr_date = date(2025, 1, 1)
    p = start_price
    np.random.seed(42)

    for i in range(n):
        while curr_date.weekday() >= 5:
            curr_date += timedelta(days=1)

        ret = np.random.normal(0.001, 0.015)
        p_next = p * (1.0 + ret)
        o = p
        c = p_next
        h = max(o, c) * 1.005
        l = min(o, c) * 0.995
        v = 50000.0 + np.random.uniform(0, 10000)

        records.append(
            OhlcvRecord(
                trading_date=curr_date,
                open=round(o, 4),
                high=round(h, 4),
                low=round(l, 4),
                close=round(c, 4),
                volume=round(v, 2),
            )
        )
        p = p_next
        curr_date += timedelta(days=1)

    return records


def test_select_pacf_lags():
    """Verify PACF selection chooses statistically significant lags."""
    np.random.seed(123)
    # Generate AR(1) returns series
    n = 200
    returns = np.zeros(n)
    for t in range(1, n):
        returns[t] = 0.5 * returns[t - 1] + np.random.normal(0, 0.01)

    selected = select_pacf_lags(returns, max_lag=10, significance_z=1.96)
    assert len(selected) > 0
    # Lag 1 should be selected for an AR(1) process
    assert 1 in selected


def test_lag_regression_model_fit_and_predict():
    """Verify LagRegressionModel StandardScaler + LASSO fitting and prediction."""
    np.random.seed(42)
    X = np.random.randn(60, 5)
    # True delta is 0.8 * X[:, 0] - 0.5 * X[:, 1]
    y = 0.8 * X[:, 0] - 0.5 * X[:, 1] + np.random.normal(0, 0.05, 60)
    feature_names = ("f1", "f2", "f3", "f4", "f5")

    model = LagRegressionModel(alpha=0.01, max_iterations=5000)
    model.fit(X, y, feature_names)

    meta = model.metadata
    assert len(meta.feature_names) == 5
    assert len(meta.coefficients) == 5
    assert meta.alpha == 0.01

    # Predict delta on new observation
    x_new = np.array([[1.0, -1.0, 0.0, 0.0, 0.0]])
    pred_delta = model.predict_delta(x_new)
    assert len(pred_delta) == 1
    # 0.8*(1) - 0.5*(-1) = 1.3, should be positive and reasonably close
    assert pred_delta[0] > 0.5


def test_refit_lir_for_production():
    """Verify refit_lir_for_production end-to-end fitting on RegressionDataset."""
    records = _generate_synthetic_series(100)
    dataset = build_regression_dataset(records, DEFAULT_LAG_REGRESSION_CONFIG.features)

    lir_fitted = refit_lir_for_production(
        dataset=dataset,
        chosen_alpha=0.01,
        config=DEFAULT_LAG_REGRESSION_CONFIG,
    )

    assert lir_fitted.model is not None
    assert len(lir_fitted.pacf_selected_lags) > 0
    assert lir_fitted.fit_metadata.alpha == 0.01


def test_arima_fit_and_append_actual():
    """Verify ARIMA offline fit and online append_actual(refit=False) sequence."""
    records = _generate_synthetic_series(80)
    closes = tuple(r.close for r in records[:60])

    spec = ArimaSpecification(order=(1, 1, 0), trend="n")
    fitted = fit_arima(closes, spec, config=DEFAULT_ARIMA_CONFIG)

    assert fitted.result is not None
    pred_1 = fitted.forecast_one()
    assert pred_1 > 0.0

    # Simulate arrival of next 5 trading days without refitting
    current = fitted
    for r in records[60:65]:
        current = current.append_actual(r.close)

    pred_next = current.forecast_one()
    assert pred_next > 0.0
    assert np.isfinite(pred_next)


def test_refit_arima_for_production():
    """Verify refit_arima_for_production fits and returns diagnostic metadata."""
    records = _generate_synthetic_series(70)
    spec = ArimaSpecification(order=(1, 1, 0), trend="n")

    prod_fit = refit_arima_for_production(
        records=records,
        selected_specification=spec,
        config=DEFAULT_ARIMA_CONFIG,
    )

    assert prod_fit.model is not None
    assert "aic" in prod_fit.fit_metadata
    assert prod_fit.fit_metadata["order"] == [1, 1, 0]
