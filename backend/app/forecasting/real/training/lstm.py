"""Explicit offline Stage-A/Stage-B training for the official Close-delta LSTM."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
import math
import random

import numpy as np
import torch
from torch import nn

from backend.app.forecasting.real.config import DEFAULT_LSTM_CONFIG, LstmConfig, LstmSpecification
from backend.app.forecasting.real.domain import OhlcvRecord, build_next_day_pairs, require_chronological_records
from backend.app.forecasting.real.models.lstm import (
    DeltaScaler,
    DeltaSequenceSample,
    FittedLstmModel,
    UnivariateDeltaLSTM,
    build_delta_sequence_samples,
    fit_delta_scaler,
    sequence_matrix,
    target_array,
    validate_model_state,
)


class LstmTrainingError(RuntimeError):
    """Raised when deterministic LSTM training cannot produce valid state."""


@dataclass(frozen=True, slots=True)
class LstmEpochMetrics:
    epoch: int
    training_mse: float
    stopping_rmse: float | None


@dataclass(frozen=True, slots=True)
class EpochSelection:
    """Fresh Stage-A epoch selection from a chronological tail only."""

    selected_epoch_count: int
    best_stopping_rmse: float
    core_target_dates: tuple[date, ...]
    stopping_target_dates: tuple[date, ...]
    scaler_mean: float
    scaler_scale: float
    epochs_trained: int
    early_stopped: bool
    metrics: tuple[LstmEpochMetrics, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "selected_epoch_count": self.selected_epoch_count,
            "best_stopping_rmse": self.best_stopping_rmse,
            "core_target_dates": [value.isoformat() for value in self.core_target_dates],
            "stopping_target_dates": [value.isoformat() for value in self.stopping_target_dates],
            "scaler_mean": self.scaler_mean,
            "scaler_scale": self.scaler_scale,
            "epochs_trained": self.epochs_trained,
            "early_stopped": self.early_stopped,
            "metrics": [
                {
                    "epoch": metric.epoch,
                    "training_mse": metric.training_mse,
                    "stopping_rmse": metric.stopping_rmse,
                }
                for metric in self.metrics
            ],
        }


@dataclass(frozen=True, slots=True)
class LstmProductionFit:
    epoch_selection: EpochSelection
    fitted: FittedLstmModel


def candidate_specifications(
    config: LstmConfig = DEFAULT_LSTM_CONFIG,
) -> tuple[LstmSpecification, ...]:
    """Return the declared 3x2x2x1 reference grid without running tuning."""
    return tuple(
        LstmSpecification(lookback, hidden_size, learning_rate, batch_size)
        for lookback in config.lookback_lengths
        for hidden_size in config.hidden_sizes
        for learning_rate in config.learning_rates
        for batch_size in config.batch_sizes
    )


def set_deterministic_controls(seed: int) -> None:
    if seed < 0:
        raise ValueError("seed cannot be negative")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True


def chronological_stopping_tail(
    samples: Sequence[DeltaSequenceSample],
    *,
    config: LstmConfig = DEFAULT_LSTM_CONFIG,
) -> tuple[tuple[DeltaSequenceSample, ...], tuple[DeltaSequenceSample, ...]]:
    chosen = tuple(samples)
    if len(chosen) < 2:
        raise LstmTrainingError("At least two samples are required for a stopping split")
    tail_size = max(
        config.minimum_stopping_samples,
        math.ceil(len(chosen) * config.stopping_tail_proportion),
    )
    tail_size = min(tail_size, len(chosen) - 1)
    core, stopping = chosen[:-tail_size], chosen[-tail_size:]
    if core[-1].target_date >= stopping[0].target_date:
        raise LstmTrainingError("Chronological stopping-tail construction failed")
    return core, stopping


def _scaled_tensors(
    samples: Sequence[DeltaSequenceSample], scaler: DeltaScaler
) -> tuple[torch.Tensor, torch.Tensor]:
    features = scaler.transform(sequence_matrix(samples))
    targets = scaler.transform(target_array(samples))
    return (
        torch.as_tensor(features, dtype=torch.float32).unsqueeze(-1),
        torch.as_tensor(targets, dtype=torch.float32),
    )


def _train_one_epoch(
    network: UnivariateDeltaLSTM,
    optimizer: torch.optim.Optimizer,
    features: torch.Tensor,
    targets: torch.Tensor,
    *,
    batch_size: int,
) -> float:
    network.train()
    loss_function = nn.MSELoss()
    total_loss = 0.0
    total_count = 0
    # Chronological slices; there is deliberately no DataLoader shuffle.
    for start in range(0, len(features), batch_size):
        batch_features = features[start : start + batch_size]
        batch_targets = targets[start : start + batch_size]
        optimizer.zero_grad(set_to_none=True)
        prediction = network(batch_features)
        loss = loss_function(prediction, batch_targets)
        if not torch.isfinite(loss):
            raise LstmTrainingError("LSTM training produced a non-finite loss")
        count = len(batch_targets)
        total_loss += float(loss.detach().item()) * count
        total_count += count
        loss.backward()
        optimizer.step()
    result = total_loss / total_count
    if not math.isfinite(result):
        raise LstmTrainingError("LSTM epoch produced a non-finite training loss")
    return result


def _scaled_rmse(
    network: UnivariateDeltaLSTM,
    features: torch.Tensor,
    targets: torch.Tensor,
) -> float:
    network.eval()
    with torch.no_grad():
        rmse = torch.sqrt(torch.mean(torch.square(targets - network(features))))
    result = float(rmse.item())
    if not math.isfinite(result):
        raise LstmTrainingError("LSTM stopping loss is non-finite")
    return result


def select_epoch_count(
    samples: Sequence[DeltaSequenceSample],
    specification: LstmSpecification,
    *,
    seed: int = 42,
    config: LstmConfig = DEFAULT_LSTM_CONFIG,
) -> EpochSelection:
    """Stage A: choose epochs on the newest chronological stopping tail."""
    core, stopping = chronological_stopping_tail(samples, config=config)
    scaler = fit_delta_scaler(core)
    core_features, core_targets = _scaled_tensors(core, scaler)
    stopping_features, stopping_targets = _scaled_tensors(stopping, scaler)
    set_deterministic_controls(seed)
    network = UnivariateDeltaLSTM(specification.hidden_size)
    optimizer = torch.optim.Adam(network.parameters(), lr=specification.learning_rate)
    best_epoch = 1
    best_rmse = math.inf
    stale_epochs = 0
    metrics: list[LstmEpochMetrics] = []
    for epoch in range(1, config.max_epochs + 1):
        training_mse = _train_one_epoch(
            network,
            optimizer,
            core_features,
            core_targets,
            batch_size=specification.batch_size,
        )
        stopping_rmse = _scaled_rmse(network, stopping_features, stopping_targets)
        if stopping_rmse < best_rmse - config.early_stopping_min_delta:
            best_rmse = stopping_rmse
            best_epoch = epoch
            stale_epochs = 0
        else:
            stale_epochs += 1
        metrics.append(LstmEpochMetrics(epoch, training_mse, stopping_rmse))
        if stale_epochs >= config.early_stopping_patience:
            break
    return EpochSelection(
        selected_epoch_count=best_epoch,
        best_stopping_rmse=best_rmse,
        core_target_dates=tuple(sample.target_date for sample in core),
        stopping_target_dates=tuple(sample.target_date for sample in stopping),
        scaler_mean=float(scaler.mean),
        scaler_scale=float(scaler.scale),
        epochs_trained=len(metrics),
        early_stopped=len(metrics) < config.max_epochs,
        metrics=tuple(metrics),
    )


def fit_fixed_epochs(
    samples: Sequence[DeltaSequenceSample],
    specification: LstmSpecification,
    *,
    epoch_count: int,
    seed: int = 42,
) -> FittedLstmModel:
    """Stage B: use a fresh scaler and model on the full supplied data block."""
    chosen = tuple(samples)
    if not chosen or epoch_count < 1:
        raise ValueError("Fixed-epoch fitting requires samples and a positive epoch count")
    scaler = fit_delta_scaler(chosen)
    features, targets = _scaled_tensors(chosen, scaler)
    set_deterministic_controls(seed)
    network = UnivariateDeltaLSTM(specification.hidden_size)
    optimizer = torch.optim.Adam(network.parameters(), lr=specification.learning_rate)
    for _ in range(epoch_count):
        _train_one_epoch(
            network,
            optimizer,
            features,
            targets,
            batch_size=specification.batch_size,
        )
    fitted = FittedLstmModel(
        network=network,
        scaler=scaler,
        specification=specification,
        epoch_count=epoch_count,
        seed=seed,
        training_size=len(chosen),
    )
    validate_model_state(fitted)
    return fitted


def refit_lstm_for_production(
    records: Sequence[OhlcvRecord],
    *,
    selected_specification: LstmSpecification,
    config: LstmConfig = DEFAULT_LSTM_CONFIG,
) -> LstmProductionFit:
    """Fresh Stage A selection followed by Stage B full-history refitting."""
    require_chronological_records(records)
    samples = build_delta_sequence_samples(
        build_next_day_pairs(records), lookback=selected_specification.lookback
    )
    stage_a = select_epoch_count(
        samples,
        selected_specification,
        seed=config.final_seed,
        config=config,
    )
    fitted = fit_fixed_epochs(
        samples,
        selected_specification,
        epoch_count=stage_a.selected_epoch_count,
        seed=config.final_seed,
    )
    return LstmProductionFit(epoch_selection=stage_a, fitted=fitted)
