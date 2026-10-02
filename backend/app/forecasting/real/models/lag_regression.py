"""StandardScaler + LASSO implementation for next-day close deltas."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sklearn.linear_model import Lasso
from sklearn.preprocessing import StandardScaler

from backend.app.forecasting.real.models.base import FloatArray, ForecastModel


@dataclass(frozen=True, slots=True)
class LagRegressionFitMetadata:
    """Parameters and statistics needed to audit and reproduce a fitted LASSO prediction."""

    alpha: float
    feature_names: tuple[str, ...]
    selected_features: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    scaler_variance: tuple[float, ...]
    iterations: int
    dual_gap: float
    converged: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "alpha": self.alpha,
            "feature_names": list(self.feature_names),
            "selected_features": list(self.selected_features),
            "coefficients": {
                name: coefficient
                for name, coefficient in zip(self.feature_names, self.coefficients, strict=False)
            },
            "intercept": self.intercept,
            "iterations": self.iterations,
            "dual_gap": self.dual_gap,
            "converged": self.converged,
            "scaler": {
                "mean": dict(zip(self.feature_names, self.scaler_mean, strict=False)),
                "scale": dict(zip(self.feature_names, self.scaler_scale, strict=False)),
                "variance": dict(zip(self.feature_names, self.scaler_variance, strict=False)),
            },
        }


class LagRegressionModel(ForecastModel):
    """LASSO fitted directly on standardized causal features."""

    def __init__(
        self,
        *,
        alpha: float,
        max_iterations: int = 100_000,
        tolerance: float = 1e-7,
        coefficient_zero_tolerance: float = 1e-12,
    ) -> None:
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        self.alpha = float(alpha)
        self.max_iterations = max_iterations
        self.tolerance = tolerance
        self.coefficient_zero_tolerance = coefficient_zero_tolerance
        self.scaler: StandardScaler | None = None
        self.estimator: Lasso | None = None
        self.feature_names: tuple[str, ...] = ()

    def fit(
        self,
        features: FloatArray,
        targets: FloatArray,
        feature_names: Sequence[str],
    ) -> "LagRegressionModel":
        matrix = np.asarray(features, dtype=np.float64)
        target_array = np.asarray(targets, dtype=np.float64).reshape(-1)
        names = tuple(feature_names)
        if matrix.ndim != 2:
            raise ValueError("features must be a two-dimensional matrix")
        if matrix.shape[0] != target_array.shape[0]:
            raise ValueError("features and targets must have the same row count")
        if matrix.shape[1] != len(names) or not names:
            raise ValueError("feature_names must match the non-empty feature matrix width")
        if not np.isfinite(matrix).all() or not np.isfinite(target_array).all():
            raise ValueError("LASSO training data must be finite")

        scaler = StandardScaler()
        scaled = scaler.fit_transform(matrix)
        estimator = Lasso(
            alpha=self.alpha,
            fit_intercept=True,
            max_iter=self.max_iterations,
            tol=self.tolerance,
            selection="cyclic",
        )
        estimator.fit(scaled, target_array)
        self.scaler = scaler
        self.estimator = estimator
        self.feature_names = names
        return self

    def predict_delta(self, features: FloatArray) -> FloatArray:
        if self.scaler is None or self.estimator is None:
            raise RuntimeError("LagRegressionModel must be fitted before prediction")
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise ValueError("Prediction feature width does not match the fitted model")
        if not np.isfinite(matrix).all():
            raise ValueError("Prediction features must be finite")
        return np.asarray(
            self.estimator.predict(self.scaler.transform(matrix)), dtype=np.float64
        ).reshape(-1)

    @property
    def metadata(self) -> LagRegressionFitMetadata:
        if self.scaler is None or self.estimator is None:
            raise RuntimeError("LagRegressionModel must be fitted before metadata is available")
        coefficients: NDArray[np.float64] = np.asarray(
            self.estimator.coef_, dtype=np.float64
        )
        selected = tuple(
            name
            for name, coefficient in zip(self.feature_names, coefficients, strict=False)
            if abs(float(coefficient)) > self.coefficient_zero_tolerance
        )
        return LagRegressionFitMetadata(
            alpha=self.alpha,
            feature_names=self.feature_names,
            selected_features=selected,
            coefficients=tuple(float(value) for value in coefficients),
            intercept=float(self.estimator.intercept_),
            scaler_mean=tuple(float(value) for value in self.scaler.mean_),
            scaler_scale=tuple(float(value) for value in self.scaler.scale_),
            scaler_variance=tuple(float(value) for value in self.scaler.var_),
            iterations=int(self.estimator.n_iter_),
            dual_gap=float(self.estimator.dual_gap_),
            converged=int(self.estimator.n_iter_) < self.max_iterations,
        )
