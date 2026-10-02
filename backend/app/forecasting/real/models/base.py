"""Base interface and reconstruction helpers for real forecasting models."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


class ForecastModel(ABC):
    """Interface implemented by real PSE Pulse forecasting models."""

    target_name = "next_day_close_delta"

    @abstractmethod
    def fit(
        self,
        features: FloatArray,
        targets: FloatArray,
        feature_names: Sequence[str],
    ) -> "ForecastModel":
        """Fit the estimator and return self."""

    @abstractmethod
    def predict_delta(self, features: FloatArray) -> FloatArray:
        """Predict next-session close deltas."""

    def predict_close(
        self,
        features: FloatArray,
        origin_closes: FloatArray,
    ) -> FloatArray:
        """Reconstruct close-level forecasts from predicted deltas."""
        predicted_deltas = self.predict_delta(features)
        origins = np.asarray(origin_closes, dtype=np.float64).reshape(-1)
        if predicted_deltas.shape != origins.shape:
            raise ValueError("origin_closes must match the number of predictions")
        return origins + predicted_deltas


def reconstruct_close(
    origin_close: float | FloatArray,
    predicted_delta: float | FloatArray,
) -> float | FloatArray:
    """Apply the authoritative delta-to-close target reconstruction: close = origin_close + delta."""
    reconstructed = np.asarray(origin_close, dtype=np.float64) + np.asarray(
        predicted_delta, dtype=np.float64
    )
    if reconstructed.ndim == 0:
        return float(reconstructed)
    return reconstructed
