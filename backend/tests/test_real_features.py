"""Unit tests for causal regression features in real forecasting engine."""

from datetime import date, timedelta
import numpy as np
import pytest

from backend.app.forecasting.real.config import RegressionFeatureConfig
from backend.app.forecasting.real.domain import OhlcvRecord
from backend.app.forecasting.real.features.regression_features import (
    RegressionDataset,
    _ema,
    _mean_std,
    build_regression_dataset,
    build_regression_origin_features,
    feature_names_for_pacf_lags,
    regression_feature_contract,
    regression_feature_names,
)


def _make_dummy_records(n: int = 100, base_price: float = 100.0) -> list[OhlcvRecord]:
    """Generate synthetic sequential records with trending price & volume."""
    records: list[OhlcvRecord] = []
    current_date = date(2025, 1, 1)
    price = base_price

    for i in range(n):
        # Skip weekends
        while current_date.weekday() >= 5:
            current_date += timedelta(days=1)

        delta = 0.5 * np.sin(i / 5.0) + 0.1
        o = price
        c = price + delta
        h = max(o, c) + 0.2
        l = min(o, c) - 0.2
        v = 10000.0 + (i * 100.0)

        records.append(
            OhlcvRecord(
                trading_date=current_date,
                open=round(o, 4),
                high=round(h, 4),
                low=round(l, 4),
                close=round(c, 4),
                volume=round(v, 2),
            )
        )
        price = c
        current_date += timedelta(days=1)

    return records


def test_regression_feature_contract_order():
    """Verify that candidate feature contract produces exactly 47 unique features in deterministic order."""
    config = RegressionFeatureConfig()
    contract = regression_feature_contract(config)

    expected_names = (
        *(f"return_lag_{i}" for i in range(1, 21)),
        "return_mean_5", "return_std_5",
        "return_mean_10", "return_std_10",
        "return_mean_20", "return_std_20",
        "volume_log", "volume_change_1",
        "volume_ratio_5", "volume_z_5",
        "volume_ratio_20", "volume_z_20",
        "range_pct", "open_close_spread_pct", "close_location_in_range",
        "close_relative_sma_5", "close_relative_sma_10", "close_relative_sma_20",
        "rsi_14", "ema_relative_12", "ema_relative_26",
        "macd_relative", "macd_signal_relative", "macd_histogram_relative",
        "bollinger_z_20", "bollinger_width_20", "bollinger_position_20",
    )

    assert config.return_lags == tuple(range(1, 21))
    assert config.raw_price_lags == ()
    assert contract.candidate_feature_names == expected_names
    assert len(expected_names) == 47

    # Verify no duplicates
    assert len(set(contract.candidate_feature_names)) == 47
    assert regression_feature_names(config) == contract.candidate_feature_names


def test_internal_indicator_helpers():
    """Verify internal math helper behavior."""
    prices = [10.0, 11.0, 12.0, 11.5, 13.0, 14.0]
    ema_vals = _ema(prices, 3)
    assert len(ema_vals) == len(prices)
    assert ema_vals[-1] > ema_vals[0]

    mean, std = _mean_std(prices)
    assert np.isclose(mean, np.mean(prices))
    assert np.isclose(std, np.std(prices))


def test_feature_names_for_pacf_lags():
    """Verify PACF lag filtering preserves other features and selects return lags."""
    config = RegressionFeatureConfig()
    all_names = regression_feature_names(config)

    filtered = feature_names_for_pacf_lags(all_names, (1, 5))
    assert "return_lag_1" in filtered
    assert "return_lag_5" in filtered
    assert "return_lag_2" not in filtered
    assert "rsi_14" in filtered  # Non-return features are kept


def test_build_regression_dataset_and_samples():
    """Verify building regression dataset produces valid labeled samples with zero lookahead."""
    records = _make_dummy_records(80)
    config = RegressionFeatureConfig()

    dataset = build_regression_dataset(records, config)
    assert len(dataset.samples) > 20

    # Check a sample
    sample = dataset.samples[0]
    assert sample.origin_date < sample.target_date
    assert sample.target_delta != 0.0

    # Ensure matrix extraction matches feature count
    matrix = dataset.matrix(dataset.samples)
    assert matrix.shape[0] == len(dataset.samples)
    assert matrix.shape[1] == 47
    assert not np.isnan(matrix).any()


def test_build_regression_origin_features_matches_dataset():
    """Verify that build_regression_origin_features produces the exact same features as the last dataset row."""
    records = _make_dummy_records(80)
    config = RegressionFeatureConfig()

    dataset = build_regression_dataset(records, config)
    last_sample = dataset.samples[-1]

    # The last sample in the dataset has target_date = records[-1].trading_date and origin_date = records[-2].trading_date
    # Therefore, origin features on records[:-1] must match last_sample.features
    prior_origin_features = build_regression_origin_features(records[:-1], config)
    assert len(prior_origin_features.feature_values) == len(last_sample.feature_values)
    for v1, v2 in zip(prior_origin_features.feature_values, last_sample.feature_values):
        assert np.isclose(v1, v2, atol=1e-5)
