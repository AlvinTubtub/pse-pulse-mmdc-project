"""Real forecasting model implementations package."""

from backend.app.forecasting.real.models.base import ForecastModel, reconstruct_close
from backend.app.forecasting.real.models.lag_regression import (
    LagRegressionFitMetadata,
    LagRegressionModel,
)
from backend.app.forecasting.real.models.arima import (
    ArimaConvergenceError,
    ArimaError,
    ArimaFitAttempt,
    ArimaFitError,
    ArimaSpecification,
    ConvergenceStatus,
    FittedArimaModel,
    candidate_specifications,
    fit_arima,
)

__all__ = [
    "ForecastModel",
    "reconstruct_close",
    "LagRegressionModel",
    "LagRegressionFitMetadata",
    "ArimaError",
    "ArimaFitError",
    "ArimaConvergenceError",
    "ConvergenceStatus",
    "ArimaSpecification",
    "ArimaFitAttempt",
    "FittedArimaModel",
    "candidate_specifications",
    "fit_arima",
]
