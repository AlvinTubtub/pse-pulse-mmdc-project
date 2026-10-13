"""Exactly-one next-PSE-session forecast per company and model."""

from collections.abc import Sequence
from datetime import date
from typing import Protocol
from typing import Any

from backend.app.forecasting.real.artifacts.schema import ProductionModelMetadata
from backend.app.forecasting.real.calendar import manila_now
from backend.app.forecasting.real.domain import (
    CompanyNextDayForecast,
    NextDayPrediction,
    OhlcvRecord,
    require_chronological_records,
)
from backend.app.forecasting.real.inference.predictor import predict_with_production_model


class ForecastCalendar(Protocol):
    def is_session(self, session_date: date) -> bool: ...
    def next_session(self, origin: date) -> date: ...


def predict_next_day_with_artifacts(
    symbol: str,
    records: Sequence[OhlcvRecord],
    loaded_artifacts: Sequence[tuple[Any, ProductionModelMetadata | dict[str, Any]]],
    *,
    calendar: ForecastCalendar,
) -> CompanyNextDayForecast:
    """Forecast next trading session from loaded, checksum-validated production artifacts."""
    history = tuple(records)
    require_chronological_records(history)
    if not history:
        raise ValueError("At least one approved historical observation is required.")

    origin_date = history[-1].trading_date
    if not calendar.is_session(origin_date):
        raise ValueError("Forecast origin is not an approved trading session.")
    origin_close = history[-1].close
    forecast_for = calendar.next_session(origin_date)
    inference_timestamp = manila_now()

    predictions: list[NextDayPrediction] = []
    for fitted_model, metadata in loaded_artifacts:
        metadata_symbol = metadata.get("symbol") if isinstance(metadata, dict) else metadata.symbol
        if metadata_symbol != symbol:
            raise ValueError(
                f"Artifact symbol mismatch: artifact is for {metadata_symbol}, expected {symbol}"
            )
        forecast = predict_with_production_model(
            fitted_model=fitted_model,
            metadata=metadata,
            records=history,
        )
        prediction = NextDayPrediction(
            symbol=symbol,
            model=forecast.model,
            origin_date=origin_date,
            forecast_for=forecast_for,
            origin_close=origin_close,
            predicted_delta=forecast.predicted_delta,
            predicted_close=forecast.predicted_close,
            inference_at=inference_timestamp,
            model_artifact_id=None,
            bundle_version=(metadata.get("model_version") if isinstance(metadata, dict) else metadata.model_version),
        )
        predictions.append(prediction)

    return CompanyNextDayForecast(
        symbol=symbol,
        origin_date=origin_date,
        forecast_for=forecast_for,
        predictions=tuple(predictions),
    )
