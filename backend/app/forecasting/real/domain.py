"""Domain types for real forecasting, next-session inference, and validation."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
import math

from backend.app.forecasting.real.config import ModelId


@dataclass(frozen=True, slots=True)
class OhlcvRecord:
    """A single chronological daily OHLCV trading session."""

    trading_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.open) or self.open <= 0:
            raise ValueError(f"Open price must be positive and finite: {self.open}")
        if not math.isfinite(self.high) or self.high <= 0:
            raise ValueError(f"High price must be positive and finite: {self.high}")
        if not math.isfinite(self.low) or self.low <= 0:
            raise ValueError(f"Low price must be positive and finite: {self.low}")
        if not math.isfinite(self.close) or self.close <= 0:
            raise ValueError(f"Close price must be positive and finite: {self.close}")
        if not math.isfinite(self.volume) or self.volume < 0:
            raise ValueError(f"Volume must be non-negative and finite: {self.volume}")
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) cannot be lower than Low ({self.low})")
        if self.high < max(self.open, self.close):
            raise ValueError(f"High ({self.high}) must be >= max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError(f"Low ({self.low}) must be <= min(open, close)")


def require_chronological_records(records: Sequence[OhlcvRecord]) -> None:
    """Validate that records are non-empty, strictly increasing in date, and duplicate-free."""
    if not records:
        raise ValueError("OHLCV record sequence cannot be empty")
    seen_dates: set[date] = set()
    prev_date: date | None = None
    for record in records:
        d = record.trading_date
        if d in seen_dates:
            raise ValueError(f"Duplicate trading date in OHLCV sequence: {d.isoformat()}")
        if prev_date is not None and d <= prev_date:
            raise ValueError(
                f"Non-chronological trading dates: {prev_date.isoformat()} followed by {d.isoformat()}"
            )
        seen_dates.add(d)
        prev_date = d


@dataclass(frozen=True, slots=True)
class NextDayForecastPair:
    """A forecast origin and its immediately following observed session."""

    origin_date: date
    target_date: date
    origin_close: float
    actual_close: float
    target_delta: float


def build_next_day_pairs(
    records: Sequence[OhlcvRecord],
) -> tuple[NextDayForecastPair, ...]:
    """Build Date[t] to Date[t+1] targets without look-ahead features."""
    require_chronological_records(records)
    if len(records) < 2:
        raise ValueError("At least two OHLCV records are required for next-day targets")

    return tuple(
        NextDayForecastPair(
            origin_date=origin.trading_date,
            target_date=target.trading_date,
            origin_close=origin.close,
            actual_close=target.close,
            target_delta=target.close - origin.close,
        )
        for origin, target in zip(records, records[1:], strict=False)
    )


@dataclass(frozen=True, slots=True)
class ModelForecast:
    """Output of a single model inference operation."""

    model: ModelId
    predicted_delta: float
    predicted_close: float


@dataclass(frozen=True, slots=True)
class NextDayPrediction:
    """Structured result for one company, model, origin, and target session."""

    symbol: str
    model: ModelId
    origin_date: date
    forecast_for: date
    origin_close: float
    predicted_delta: float
    predicted_close: float
    inference_at: datetime
    model_artifact_id: str | None = None
    bundle_version: str | None = None

    def as_dict(self) -> dict[str, str | float | None]:
        return {
            "symbol": self.symbol,
            "model": self.model.value,
            "origin_date": self.origin_date.isoformat(),
            "forecastFor": self.forecast_for.isoformat(),
            "origin_close": self.origin_close,
            "predicted_delta": self.predicted_delta,
            "predicted_close": self.predicted_close,
            "inference_at": self.inference_at.isoformat(),
            "model_artifact_id": self.model_artifact_id,
            "bundle_version": self.bundle_version,
        }


@dataclass(frozen=True, slots=True)
class CompanyNextDayForecast:
    """Aggregated next-session forecast set for one equity."""

    symbol: str
    origin_date: date
    forecast_for: date
    predictions: tuple[NextDayPrediction, ...]

    def prediction_for(self, model: ModelId) -> NextDayPrediction:
        try:
            return {p.model: p for p in self.predictions}[model]
        except KeyError as exc:
            raise ValueError(f"Missing next-day forecast for model {model.value}") from exc

    def as_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "origin_date": self.origin_date.isoformat(),
            "forecastFor": self.forecast_for.isoformat(),
            "predictions": [p.as_dict() for p in self.predictions],
        }
