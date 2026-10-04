"""Method-parity tests for opt-in official PyTorch LSTM functionality."""

from datetime import date, timedelta
import math

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="Install backend/requirements-lstm.txt")

from backend.app.forecasting.real.config import DEFAULT_LSTM_CONFIG, LstmConfig, LstmSpecification
from backend.app.forecasting.real.domain import NextDayForecastPair, OhlcvRecord
from backend.app.forecasting.real.models.lstm import (
    DeltaScaler,
    UnivariateDeltaLSTM,
    build_delta_sequence_samples,
    fit_delta_scaler,
    sequence_matrix,
    target_array,
    validate_model_state,
)
from backend.app.forecasting.real.training.lstm import (
    candidate_specifications,
    chronological_stopping_tail,
    fit_fixed_epochs,
    refit_lstm_for_production,
    select_epoch_count,
)


def _pairs(count: int = 32) -> tuple[NextDayForecastPair, ...]:
    dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(count + 1)]
    closes = [100.0 + index * 0.3 + math.sin(index) for index in range(count + 1)]
    return tuple(
        NextDayForecastPair(
            origin_date=dates[index],
            target_date=dates[index + 1],
            origin_close=closes[index],
            actual_close=closes[index + 1],
            target_delta=closes[index + 1] - closes[index],
        )
        for index in range(count)
    )


def _records(count: int = 42) -> tuple[OhlcvRecord, ...]:
    dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(count)]
    closes = [100.0 + index * 0.3 + math.sin(index) for index in range(count)]
    return tuple(
        OhlcvRecord(
            trading_date=dates[index],
            open=closes[index],
            high=closes[index] + 1,
            low=closes[index] - 1,
            close=closes[index],
            volume=1000,
        )
        for index in range(count)
    )


def _small_config() -> LstmConfig:
    return LstmConfig(max_epochs=4, early_stopping_patience=2, minimum_stopping_samples=3)


def test_official_lstm_config_and_reference_candidate_grid():
    config = DEFAULT_LSTM_CONFIG
    assert config.lookback_lengths == (5, 10, 20)
    assert config.hidden_sizes == (16, 32)
    assert config.learning_rates == (0.001, 0.003)
    assert config.batch_sizes == (32,)
    assert config.tuning_seeds == (11, 29, 47)
    assert config.cv_splits == 5
    assert config.max_epochs == 100
    assert config.early_stopping_patience == 10
    assert config.early_stopping_min_delta == 1e-6
    assert config.stopping_tail_proportion == 0.15
    assert config.minimum_stopping_samples == 5
    assert config.final_seed == 42
    assert len(candidate_specifications(config)) == 12
    assert {spec.learning_rate for spec in candidate_specifications(config)} == {0.001, 0.003}


def test_sequence_builder_uses_past_close_deltas_and_immediate_target():
    samples = build_delta_sequence_samples(_pairs(12), lookback=5)
    assert len(samples) == 7
    first = samples[0]
    assert first.input_deltas == tuple(pair.target_delta for pair in _pairs(12)[:5])
    assert first.target_delta == _pairs(12)[5].target_delta
    assert first.origin_date == _pairs(12)[5].origin_date
    assert first.target_date == _pairs(12)[5].target_date
    assert sequence_matrix(samples).shape == (7, 5)
    assert target_array(samples).shape == (7,)
    assert all(len(sample.input_deltas) == 5 for sample in samples)


def test_sequence_builder_rejects_short_lookback_breaks_and_nonfinite_values():
    with pytest.raises(ValueError, match="Not enough"):
        build_delta_sequence_samples(_pairs(5), lookback=5)
    pairs = list(_pairs(10))
    broken = pairs[4]
    pairs[4] = NextDayForecastPair(
        broken.origin_date,
        broken.target_date + timedelta(days=1),
        broken.origin_close,
        broken.actual_close,
        broken.target_delta,
    )
    with pytest.raises(ValueError, match="contiguous"):
        build_delta_sequence_samples(pairs, lookback=3)
    with pytest.raises(ValueError, match="positive"):
        build_delta_sequence_samples(_pairs(), lookback=0)
    bad = list(_pairs(10))
    bad[0] = NextDayForecastPair(
        bad[0].origin_date,
        bad[0].target_date,
        bad[0].origin_close,
        bad[0].actual_close,
        float("nan"),
    )
    with pytest.raises(ValueError, match="finite"):
        build_delta_sequence_samples(bad, lookback=3)


def test_delta_scaler_uses_population_std_and_zero_scale_fallback():
    scaler = DeltaScaler().fit([1, 2, 3, 4])
    assert scaler.mean == 2.5
    assert scaler.scale == np.std([1, 2, 3, 4], ddof=0)
    values = np.array([-1.0, 0.0, 1.0])
    assert np.allclose(scaler.inverse_transform(scaler.transform(values)), values)
    constant = DeltaScaler().fit([4, 4, 4])
    assert constant.scale == 1.0
    assert constant.observations == 3
    with pytest.raises(ValueError, match="finite"):
        DeltaScaler().fit([1, float("inf")])


def test_scaler_is_fit_only_to_declared_contiguous_training_block():
    samples = build_delta_sequence_samples(_pairs(20), lookback=4)
    core, stopping = samples[:10], samples[10:]
    scaler = fit_delta_scaler(core)
    expected_values = tuple(core[0].input_deltas) + tuple(s.target_delta for s in core)
    assert scaler.observations == len(core) + 4
    assert scaler.mean == pytest.approx(float(np.mean(expected_values)))
    assert scaler.mean != pytest.approx(
        float(np.mean(expected_values + tuple(s.target_delta for s in stopping)))
    )
    with pytest.raises(ValueError, match="contiguous"):
        fit_delta_scaler((samples[0], samples[2]))


def test_network_architecture_and_input_shape_match_official_contract():
    network = UnivariateDeltaLSTM(hidden_size=16)
    assert network.lstm.input_size == 1
    assert network.lstm.hidden_size == 16
    assert network.lstm.batch_first is True
    assert network.lstm.num_layers == 1
    assert network.lstm.bidirectional is False
    assert isinstance(network.output, torch.nn.Linear)
    assert network.output.in_features == 16 and network.output.out_features == 1
    assert list(network(torch.ones((3, 5, 1))).shape) == [3]
    with pytest.raises(ValueError, match="shape"):
        network(torch.ones((3, 5, 2)))


def test_stopping_tail_and_stage_a_stage_b_are_chronological_and_distinct():
    samples = build_delta_sequence_samples(_pairs(48), lookback=5)
    config = _small_config()
    core, stopping = chronological_stopping_tail(samples, config=config)
    assert core[-1].target_date < stopping[0].target_date
    spec = LstmSpecification(5, 16, 0.003, 32)
    stage_a = select_epoch_count(samples, spec, seed=42, config=config)
    assert 1 <= stage_a.selected_epoch_count <= config.max_epochs
    assert stage_a.core_target_dates[-1] < stage_a.stopping_target_dates[0]
    stage_b = fit_fixed_epochs(
        samples,
        spec,
        epoch_count=stage_a.selected_epoch_count,
        seed=42,
    )
    assert stage_b.training_size == len(samples)
    assert stage_b.epoch_count == stage_a.selected_epoch_count
    assert stage_b.scaler.observations == len(samples) + spec.lookback
    validate_model_state(stage_b)
    assert np.isfinite(stage_b.predict_delta(samples[-2:])).all()
    assert np.isfinite(stage_b.predict_close(samples[-2:])).all()


def test_deterministic_cpu_fixed_epoch_refit_repeats_predictions():
    samples = build_delta_sequence_samples(_pairs(28), lookback=5)
    spec = LstmSpecification(5, 16, 0.003, 32)
    first = fit_fixed_epochs(samples, spec, epoch_count=3, seed=42)
    second = fit_fixed_epochs(samples, spec, epoch_count=3, seed=42)
    assert np.allclose(
        first.predict_delta(samples[-3:]),
        second.predict_delta(samples[-3:]),
        rtol=1e-6,
        atol=1e-7,
    )


def test_production_refit_reselects_epoch_count_from_full_history():
    fit = refit_lstm_for_production(
        _records(),
        selected_specification=LstmSpecification(5, 16, 0.003, 32),
        config=_small_config(),
    )
    assert fit.epoch_selection.selected_epoch_count == fit.fitted.epoch_count
    assert fit.fitted.seed == 42
    assert fit.fitted.training_size == len(_records()) - 1 - 5
