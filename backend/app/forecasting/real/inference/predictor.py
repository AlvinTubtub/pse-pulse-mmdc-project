"""Compatible production-artifact inference for LIR and ARIMA models."""

from collections.abc import Mapping, Sequence
import math
from typing import Any

import numpy as np

from backend.app.forecasting.real.artifacts.loader import validate_artifact_against_history
from backend.app.forecasting.real.artifacts.schema import ModelArtifactCompatibilityError, ProductionModelMetadata
from backend.app.forecasting.real.config import ModelId, RegressionFeatureConfig
from backend.app.forecasting.real.domain import ModelForecast, OhlcvRecord, require_chronological_records
from backend.app.forecasting.real.features.regression_features import build_regression_origin_features
from backend.app.forecasting.real.models.arima import FittedArimaModel
from backend.app.forecasting.real.training.refit_lir import LIRFittedModel


def _regression_feature_config(payload: object) -> RegressionFeatureConfig:
    if not isinstance(payload, Mapping):
        return RegressionFeatureConfig()
    values = dict(payload)
    tuple_fields = (
        "return_lags",
        "rolling_return_windows",
        "volume_windows",
        "raw_price_lags",
    )
    try:
        for field in tuple_fields:
            if field in values and isinstance(values[field], (list, tuple)):
                values[field] = tuple(values[field])
        return RegressionFeatureConfig(**values)
    except (TypeError, ValueError) as exc:
        raise ModelArtifactCompatibilityError(
            f"LIR feature configuration in artifact metadata is incompatible: {exc}"
        ) from exc


def predict_with_production_model(
    *,
    fitted_model: Any,
    metadata: ProductionModelMetadata | Mapping[str, Any],
    records: Sequence[OhlcvRecord],
) -> ModelForecast:
    """Generate one next-session Close forecast from one verified production model."""
    if isinstance(metadata, Mapping):
        # LSTM metadata stays JSON-native so this module remains PyTorch-free.
        try:
            trained_through = metadata["trained_through"]
            row_count = metadata["data_row_count"]
            symbol = metadata["symbol"]
            model_code = metadata["model_code"]
        except KeyError as exc:
            raise ModelArtifactCompatibilityError("Incomplete LSTM runtime metadata") from exc
        history = tuple(records)
        require_chronological_records(history)
        if history[0].trading_date.isoformat() > trained_through:
            raise ModelArtifactCompatibilityError("History does not reach the model training boundary")
        if len(history) < row_count or history[row_count - 1].trading_date.isoformat() != trained_through:
            raise ModelArtifactCompatibilityError("LSTM training boundary is incompatible with history")
    else:
        history = validate_artifact_against_history(metadata, records)
    origin_close = history[-1].close
    code_upper = (metadata["model_code"] if isinstance(metadata, Mapping) else metadata.model_code).upper()
    model_code = metadata["model_code"] if isinstance(metadata, Mapping) else metadata.model_code

    if code_upper in ("LAG_REGRESSION", "LAG_REG"):
        if not isinstance(fitted_model, LIRFittedModel):
            raise ModelArtifactCompatibilityError("Invalid in-memory LIR model instance")
        feature_config = _regression_feature_config(
            metadata.hyperparameters.get("feature_config")
        )
        origin = build_regression_origin_features(history, feature_config)
        by_name = dict(zip(origin.feature_names, origin.feature_values, strict=True))
        try:
            matrix = np.asarray(
                [[by_name[name] for name in fitted_model.fit_metadata.feature_names]],
                dtype=np.float64,
            )
        except KeyError as exc:
            raise ModelArtifactCompatibilityError(
                f"Missing LIR inference feature in origin data: {exc.args[0]}"
            ) from exc

        predicted_delta = float(fitted_model.model.predict_delta(matrix)[0])
        predicted_close = origin_close + predicted_delta
        model_id = ModelId.LAG_REGRESSION

    elif code_upper == "ARIMA":
        if not isinstance(fitted_model, FittedArimaModel):
            raise ModelArtifactCompatibilityError("Invalid in-memory ARIMA model instance")
        # Step through observations since training boundary without refitting
        current = fitted_model
        for observation in history[metadata.data_row_count :]:
            current = current.append_actual(observation.close)
        predicted_close = current.forecast_one()
        predicted_delta = predicted_close - origin_close
        model_id = ModelId.ARIMA

    elif code_upper == "LSTM":
        # The fitted model implementation imports torch in lstm_state only when it is loaded.
        if not hasattr(fitted_model, "predict_delta_sequences"):
            raise ModelArtifactCompatibilityError("Invalid in-memory LSTM model instance")
        hyperparameters = metadata["hyperparameters"] if isinstance(metadata, Mapping) else metadata.hyperparameters
        lookback = hyperparameters.get("lookback")
        if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1:
            raise ModelArtifactCompatibilityError("Invalid LSTM lookback in metadata")
        if len(history) < lookback + 1:
            raise ModelArtifactCompatibilityError("Insufficient observed history for LSTM lookback")
        latest_deltas = np.asarray(
            [history[index].close - history[index - 1].close for index in range(len(history) - lookback, len(history))],
            dtype=np.float64,
        )
        if latest_deltas.shape != (lookback,) or not np.isfinite(latest_deltas).all():
            raise ModelArtifactCompatibilityError("Invalid causal LSTM inference sequence")
        predicted_delta = float(fitted_model.predict_delta_sequences(latest_deltas.reshape(1, -1))[0])
        predicted_close = origin_close + predicted_delta
        model_id = ModelId.LSTM

    else:
        raise ModelArtifactCompatibilityError(f"Unsupported model code: {model_code}")

    if not math.isfinite(predicted_delta) or not math.isfinite(predicted_close):
        raise RuntimeError(f"{model_code} produced non-finite prediction values")
    if predicted_close <= 0:
        raise RuntimeError(f"{model_code} produced non-positive close: {predicted_close}")

    return ModelForecast(
        model=model_id,
        predicted_delta=predicted_delta,
        predicted_close=predicted_close,
    )
