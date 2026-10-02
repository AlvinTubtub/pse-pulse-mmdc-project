"""statsmodels ARIMA fitting and one-step state-update primitives."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Any
import warnings

import numpy as np
from statsmodels.tsa.arima.model import ARIMA, ARIMAResults

from backend.app.forecasting.real.config import ArimaConfig


class ArimaError(RuntimeError):
    """Base exception for an explicit ARIMA pipeline failure."""


class ArimaFitError(ArimaError):
    """Raised when every configured optimization attempt fails."""


class ArimaConvergenceError(ArimaFitError):
    """Raised when no optimization attempt supplies acceptable convergence."""


class ConvergenceStatus(StrEnum):
    """Evidence states kept distinct instead of treating missing as success."""

    CONFIRMED_CONVERGED = "confirmed_converged"
    CONFIRMED_NON_CONVERGED = "confirmed_non_converged"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True, order=True)
class ArimaSpecification:
    """One explicit ARIMA order and deterministic-term choice."""

    order: tuple[int, int, int]
    trend: str

    @property
    def drift_enabled(self) -> bool:
        """Identify the standard linear-trend representation of ARIMA drift."""
        return self.order[1] == 1 and self.trend in {"t", "ct"}

    def as_dict(self) -> dict[str, object]:
        return {
            "order": list(self.order),
            "trend": self.trend,
            "drift_enabled": self.drift_enabled,
        }


@dataclass(frozen=True, slots=True)
class ArimaFitAttempt:
    """Convergence evidence from one optimizer attempt."""

    max_iterations: int
    status: ConvergenceStatus
    optimizer_details: dict[str, object]
    exception: str | None = None
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "max_iterations": self.max_iterations,
            "status": self.status.value,
            "optimizer_details": self.optimizer_details,
            "exception": self.exception,
            "warnings": list(self.warnings),
        }


def candidate_specifications(config: ArimaConfig) -> tuple[ArimaSpecification, ...]:
    """Enumerate the complete configured grid, including ARIMA(0,d,0)."""
    return tuple(
        ArimaSpecification(order=(p, d, q), trend=trend)
        for p in config.p_values
        for d in config.d_values
        for q in config.q_values
        for trend in config.trends_for_d(d)
    )


def _json_scalar(value: Any) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    return str(value)


def convergence_status(result: object) -> tuple[ConvergenceStatus, dict[str, object]]:
    """Extract optimizer evidence without equating absent evidence with convergence."""
    raw = getattr(result, "mle_retvals", None)
    if not isinstance(raw, Mapping):
        return ConvergenceStatus.UNAVAILABLE, {}
    details = {str(key): _json_scalar(value) for key, value in raw.items()}
    converged = raw.get("converged")
    if converged is True or (
        isinstance(converged, np.bool_) and bool(converged)
    ):
        return ConvergenceStatus.CONFIRMED_CONVERGED, details
    if converged is False or (
        isinstance(converged, np.bool_) and not bool(converged)
    ):
        return ConvergenceStatus.CONFIRMED_NON_CONVERGED, details
    return ConvergenceStatus.UNAVAILABLE, details


@dataclass(slots=True)
class FittedArimaModel:
    """A fitted Close-level ARIMA result with append-only evaluation updates."""

    result: ARIMAResults
    specification: ArimaSpecification
    attempts: tuple[ArimaFitAttempt, ...]

    @property
    def convergence(self) -> ConvergenceStatus:
        return self.attempts[-1].status

    def forecast_one(self) -> float:
        """Forecast one next observation from the current state."""
        forecast = np.asarray(self.result.forecast(steps=1), dtype=np.float64).reshape(-1)
        if forecast.size != 1 or not np.isfinite(forecast[0]):
            raise ArimaFitError("ARIMA produced an invalid one-step forecast")
        return float(forecast[0])

    def append_actual(self, actual_close: float) -> "FittedArimaModel":
        """Reveal one observation and update state without re-estimating parameters."""
        actual = float(actual_close)
        if not math.isfinite(actual):
            raise ValueError("actual_close must be finite")
        updated = self.result.append([actual], refit=False)
        return FittedArimaModel(
            result=updated,
            specification=self.specification,
            attempts=self.attempts,
        )

    def fit_metadata(self) -> dict[str, object]:
        """Return JSON-safe parameters and diagnostics for reproducibility."""
        parameter_names = tuple(str(name) for name in self.result.param_names)
        parameter_values = np.asarray(self.result.params, dtype=np.float64).reshape(-1)
        return {
            **self.specification.as_dict(),
            "nobs": int(self.result.nobs),
            "aic": _json_scalar(getattr(self.result, "aic", None)),
            "bic": _json_scalar(getattr(self.result, "bic", None)),
            "hqic": _json_scalar(getattr(self.result, "hqic", None)),
            "log_likelihood": _json_scalar(getattr(self.result, "llf", None)),
            "parameters": {
                name: _json_scalar(value)
                for name, value in zip(parameter_names, parameter_values, strict=True)
            },
            "convergence_status": self.convergence.value,
            "fit_attempts": [attempt.as_dict() for attempt in self.attempts],
        }


def _validated_close_series(close_values: Sequence[float]) -> np.ndarray:
    values = np.asarray(close_values, dtype=np.float64).reshape(-1)
    if values.size < 3:
        raise ValueError("ARIMA requires at least three chronological Close values")
    if not np.isfinite(values).all():
        raise ValueError("ARIMA Close values must all be finite")
    if np.any(values <= 0):
        raise ValueError("ARIMA Close values must all be positive")
    return values


def fit_arima(
    close_values: Sequence[float],
    specification: ArimaSpecification,
    *,
    config: ArimaConfig,
) -> FittedArimaModel:
    """Fit ARIMA with configured retries and strict convergence requirements."""
    values = _validated_close_series(close_values)
    attempts: list[ArimaFitAttempt] = []
    successful_but_unconfirmed: tuple[ARIMAResults, ArimaFitAttempt] | None = None
    for max_iterations in config.retry_max_iterations:
        try:
            model = ARIMA(
                values,
                order=specification.order,
                trend=specification.trend,
                enforce_stationarity=config.enforce_stationarity,
                enforce_invertibility=config.enforce_invertibility,
            )
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                result = model.fit(
                    method_kwargs={"maxiter": max_iterations, "disp": 0}
                )
            status, details = convergence_status(result)
            attempt = ArimaFitAttempt(
                max_iterations=max_iterations,
                status=status,
                optimizer_details=details,
                warnings=tuple(str(item.message) for item in caught_warnings),
            )
            attempts.append(attempt)
            if status is ConvergenceStatus.CONFIRMED_CONVERGED:
                return FittedArimaModel(result, specification, tuple(attempts))
            if status is ConvergenceStatus.UNAVAILABLE:
                successful_but_unconfirmed = (result, attempt)
        except Exception as exc:
            attempts.append(
                ArimaFitAttempt(
                    max_iterations=max_iterations,
                    status=ConvergenceStatus.UNAVAILABLE,
                    optimizer_details={},
                    exception=f"{type(exc).__name__}: {exc}",
                )
            )

    if not config.require_confirmed_convergence and successful_but_unconfirmed:
        result, _ = successful_but_unconfirmed
        return FittedArimaModel(result, specification, tuple(attempts))
    statuses = ", ".join(attempt.status.value for attempt in attempts)
    raise ArimaConvergenceError(
        f"ARIMA{specification.order} trend={specification.trend!r} did not provide "
        f"acceptable convergence after {len(attempts)} attempt(s): {statuses}"
    )
