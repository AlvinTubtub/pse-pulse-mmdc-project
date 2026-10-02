"""Deterministic expanding-window folds and causal PACF lag selection."""

from dataclasses import dataclass
import math

import numpy as np
from numpy.typing import NDArray
from statsmodels.tsa.stattools import pacf

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class ExpandingWindowFold:
    """Contiguous training and validation positions with an expanding origin."""

    fold_index: int
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]


def expanding_window_folds(
    n_samples: int,
    *,
    n_splits: int,
) -> tuple[ExpandingWindowFold, ...]:
    """Create chronological folds without shuffling or future reuse."""
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2")
    if n_samples < n_splits + 1:
        raise ValueError(
            f"Need at least {n_splits + 1} samples for {n_splits} chronological folds"
        )

    validation_size = max(1, n_samples // (n_splits + 1))
    initial_train_size = n_samples - n_splits * validation_size
    folds: list[ExpandingWindowFold] = []
    for fold_index in range(n_splits):
        validation_start = initial_train_size + fold_index * validation_size
        validation_end = validation_start + validation_size
        folds.append(
            ExpandingWindowFold(
                fold_index=fold_index,
                train_indices=tuple(range(validation_start)),
                validation_indices=tuple(range(validation_start, validation_end)),
            )
        )
    return tuple(folds)


def select_pacf_lags(
    training_returns: FloatArray,
    *,
    max_lag: int = 20,
    significance_z: float = 1.96,
) -> tuple[int, ...]:
    """Select significant PACF lags from training returns only.

    Uses statsmodels Yule-Walker sample PACF. Standard error is approximated as
    1 / sqrt(N). Lags with absolute PACF exceeding z / sqrt(N) are retained.
    Falls back to lag 1 if no lag crosses the significance threshold.
    """
    values = np.asarray(training_returns, dtype=np.float64).reshape(-1)
    if values.size < 4:
        raise ValueError("At least four training returns are required for PACF")
    if not np.isfinite(values).all():
        raise ValueError("PACF training returns must be finite")
    usable_max_lag = min(max_lag, max(1, values.size // 2 - 1))
    coefficients = pacf(values, nlags=usable_max_lag, method="ywmle")
    threshold = significance_z / math.sqrt(values.size)
    selected = tuple(
        lag
        for lag in range(1, usable_max_lag + 1)
        if abs(float(coefficients[lag])) > threshold
    )
    # A single most-recent return keeps the configured lag family represented
    # when no lag crosses the finite-sample significance threshold.
    return selected or (1,)
