"""Exactly-one next-PSE-session forecast per company and model."""

from collections.abc import Sequence
from datetime import date
from typing import Any

from backend.app.forecasting.real.artifacts.schema import ProductionModelMetadata
from backend.app.forecasting.real.calendar import PSETradingCalendar, manila_now
from backend.app.forecasting.real.domain import (
    CompanyNextDayForecast,
    NextDayPrediction,
    OhlcvRecord,
    require_chronological_records,
)
from backend.app.forecasting.real.inference.predictor import predict_with_production_model


def predict_next_day_with_artifacts(
    symbol: str,
    records: Sequence[OhlcvRecord],
    loaded_artifacts: Sequence[tuple[Any, ProductionModelMetadata]],
    *,
    calendar: PSETradingCalendar | None = None,
) -> CompanyNextDayForecast:
    """Forecast next trading session from loaded, checksum-validated production artifacts."""
    history = tuple(records)
    require_chronological_records(history)
    cal = calendar or PSETradingCalendar()

    origin_date = history[-1].trading_date
    origin_close = history[-1].close
    forecast_for = cal.next_trading_day(origin_date)
    inference_timestamp = manila_now()

    predictions: list[NextDayPrediction] = []
    for fitted_model, metadata in loaded_artifacts:
        if metadata.symbol != symbol:
            raise ValueError(
                f"Artifact symbol mismatch: artifact is for {metadata.symbol}, expected {symbol}"
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
            bundle_version=metadata.model_version,
        )
        predictions.append(prediction)

    return CompanyNextDayForecast(
        symbol=symbol,
        origin_date=origin_date,
        forecast_for=forecast_for,
        predictions=tuple(predictions),
    )
