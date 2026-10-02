"""Safe, checksum-verified loading of production model artifacts.

NEVER executes joblib.load() before:
1. Safe-path validation (prevent directory traversal)
2. JSON metadata schema and type validation
3. Symbol and model-code validation
4. Schema version and implementation version validation
5. Cryptographic SHA-256 verification of the serialized binary against metadata
6. Model-class and training-boundary checks
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import json
import logging
from pathlib import Path
from typing import Any

import joblib

from backend.app.forecasting.real.artifacts.schema import (
    MODEL_ARTIFACT_SCHEMA_ID,
    MODEL_ARTIFACT_SCHEMA_VERSION,
    MODEL_IMPLEMENTATION_VERSION,
    ModelArtifactCompatibilityError,
    ProductionModelMetadata,
)
from backend.app.forecasting.real.artifacts.writer import compute_artifact_sha256
from backend.app.forecasting.real.domain import OhlcvRecord, require_chronological_records
from backend.app.forecasting.real.models.arima import FittedArimaModel
from backend.app.forecasting.real.training.refit_lir import LIRFittedModel

LOGGER = logging.getLogger(__name__)


def validate_model_artifact_metadata(
    payload: Mapping[str, Any],
    *,
    expected_symbol: str,
    expected_model_code: str,
    expected_model_version: str | None = None,
) -> ProductionModelMetadata:
    """Validate metadata schema, identity, dates, format, and required hyperparameters."""
    if payload.get("schema_id") != MODEL_ARTIFACT_SCHEMA_ID:
        raise ModelArtifactCompatibilityError(
            f"Unsupported model artifact schema_id: {payload.get('schema_id')}"
        )
    if payload.get("schema_version") != MODEL_ARTIFACT_SCHEMA_VERSION:
        raise ModelArtifactCompatibilityError(
            f"Unsupported model artifact schema_version: {payload.get('schema_version')}"
        )
    if payload.get("implementation_version") != MODEL_IMPLEMENTATION_VERSION:
        raise ModelArtifactCompatibilityError(
            f"Unsupported model implementation version: {payload.get('implementation_version')}"
        )
    if payload.get("symbol") != expected_symbol:
        raise ModelArtifactCompatibilityError(
            f"Model artifact symbol mismatch: expected {expected_symbol}, got {payload.get('symbol')}"
        )
    if payload.get("model_code") != expected_model_code:
        raise ModelArtifactCompatibilityError(
            f"Model artifact model_code mismatch: expected {expected_model_code}, got {payload.get('model_code')}"
        )
    if expected_model_version is not None and payload.get("model_version") != expected_model_version:
        raise ModelArtifactCompatibilityError(
            f"Model artifact model_version mismatch: expected {expected_model_version}, got {payload.get('model_version')}"
        )

    if payload.get("artifact_format") != "joblib":
        raise ModelArtifactCompatibilityError(
            f"Unsupported artifact_format: {payload.get('artifact_format')}"
        )

    artifact_filename = payload.get("artifact_filename")
    if (
        not isinstance(artifact_filename, str)
        or Path(artifact_filename).name != artifact_filename
        or "/" in artifact_filename
        or "\\" in artifact_filename
        or not artifact_filename.endswith(".joblib")
    ):
        raise ModelArtifactCompatibilityError(
            f"Unsafe or invalid artifact_filename: {artifact_filename}"
        )

    artifact_sha = payload.get("artifact_sha256")
    if (
        not isinstance(artifact_sha, str)
        or len(artifact_sha) != 64
        or any(c not in "0123456789abcdef" for c in artifact_sha.lower())
    ):
        raise ModelArtifactCompatibilityError(
            f"Invalid artifact_sha256 in metadata: {artifact_sha}"
        )

    try:
        trained_through = date.fromisoformat(str(payload["trained_through"]))
        created_at = datetime.fromisoformat(str(payload["created_at"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelArtifactCompatibilityError(
            f"Invalid trained_through date or created_at timestamp: {exc}"
        ) from exc

    if created_at.tzinfo is None:
        raise ModelArtifactCompatibilityError("Creation timestamp must be timezone-aware")

    data_row_count = payload.get("data_row_count")
    if (
        isinstance(data_row_count, bool)
        or not isinstance(data_row_count, int)
        or data_row_count < 1
    ):
        raise ModelArtifactCompatibilityError("data_row_count must be a positive integer")

    hyperparameters = payload.get("hyperparameters")
    if not isinstance(hyperparameters, dict) or not hyperparameters:
        raise ModelArtifactCompatibilityError("Missing model hyperparameters dictionary")

    # Model-family specific required hyperparameters
    code_upper = expected_model_code.upper()
    if code_upper in ("LAG_REGRESSION", "LAG_REG"):
        required_keys = {"alpha", "feature_names", "pacf_selected_lags"}
    elif code_upper == "ARIMA":
        required_keys = {"order", "trend"}
    else:
        required_keys = set()

    if not required_keys <= set(hyperparameters.keys()):
        missing_keys = required_keys - set(hyperparameters.keys())
        raise ModelArtifactCompatibilityError(
            f"Missing required hyperparameters for {expected_model_code}: {missing_keys}"
        )

    return ProductionModelMetadata(
        symbol=expected_symbol,
        model_code=expected_model_code,
        model_version=str(payload["model_version"]),
        trained_through=trained_through,
        data_row_count=data_row_count,
        hyperparameters=hyperparameters,
        created_at=created_at,
        artifact_format="joblib",
        artifact_filename=artifact_filename,
        artifact_sha256=artifact_sha.lower(),
        schema_id=str(payload["schema_id"]),
        schema_version=int(payload["schema_version"]),
        implementation_version=str(payload["implementation_version"]),
        source_repository=str(payload.get("source_repository", "")),
        source_commit=str(payload.get("source_commit", "")),
        historical_data_source_repository=str(payload.get("historical_data_source_repository", "")),
        historical_data_source_commit=str(payload.get("historical_data_source_commit", "")),
    )


def load_production_model(
    *,
    symbol_directory: Path,
    expected_symbol: str,
    expected_model_code: str,
    expected_model_version: str | None = None,
) -> tuple[Any, ProductionModelMetadata]:
    """Load a production model artifact with mandatory pre-deserialization SHA-256 verification.

    Steps:
    1. Resolve and validate directory safety.
    2. Read and parse metadata JSON.
    3. Validate metadata fields against expected symbol, model code, version.
    4. Validate binary file existence and compute SHA-256.
    5. Compare computed SHA-256 against metadata SHA-256 (fail-closed if mismatch).
    6. ONLY AFTER SHA-256 MATCHES: deserialize via joblib.load().
    7. Verify loaded model object matches expected class and internal hyperparameters.

    Returns (fitted_model, metadata).
    """
    directory = symbol_directory.resolve()
    if not directory.is_dir():
        raise ModelArtifactCompatibilityError(
            f"Model directory does not exist or is not a directory: {directory}"
        )

    metadata_path = directory / f"{expected_model_code.lower()}.metadata.json"
    if not metadata_path.is_file():
        if expected_model_code.lower() in ("lag_reg", "lag_regression"):
            alt_code = "lag_regression" if expected_model_code.lower() == "lag_reg" else "lag_reg"
            alt_path = directory / f"{alt_code}.metadata.json"
            if alt_path.is_file():
                metadata_path = alt_path
    if not metadata_path.is_file():
        raise ModelArtifactCompatibilityError(
            f"Metadata file missing at {metadata_path}"
        )

    try:
        with metadata_path.open("r", encoding="utf-8") as f:
            raw_metadata = json.load(f)
    except Exception as exc:
        raise ModelArtifactCompatibilityError(
            f"Failed to read or parse metadata JSON at {metadata_path}: {exc}"
        ) from exc

    if not isinstance(raw_metadata, Mapping):
        raise ModelArtifactCompatibilityError("Metadata JSON root must be a mapping object")

    # Step 3: Validate metadata
    metadata = validate_model_artifact_metadata(
        raw_metadata,
        expected_symbol=expected_symbol,
        expected_model_code=expected_model_code,
        expected_model_version=expected_model_version,
    )

    # Step 4: Validate binary path safety
    model_path = (directory / metadata.artifact_filename).resolve()
    if model_path.parent != directory:
        raise ModelArtifactCompatibilityError(
            f"Path traversal detected: {model_path} escapes {directory}"
        )
    if not model_path.is_file():
        raise ModelArtifactCompatibilityError(
            f"Model binary file missing at {model_path}"
        )

    # Step 5: Pre-load SHA-256 verification
    actual_sha = compute_artifact_sha256(model_path)
    if actual_sha != metadata.artifact_sha256:
        raise ModelArtifactCompatibilityError(
            f"SHA-256 checksum mismatch for {model_path.name}: "
            f"computed '{actual_sha}' != metadata '{metadata.artifact_sha256}'"
        )

    # Step 6: ONLY AFTER VERIFICATION: deserialize binary
    try:
        fitted_model = joblib.load(model_path)
    except Exception as exc:
        raise ModelArtifactCompatibilityError(
            f"Failed to load verified model binary {model_path}: {exc}"
        ) from exc

    # Step 7: Verify model class and hyperparameters
    code_upper = expected_model_code.upper()
    if code_upper in ("LAG_REGRESSION", "LAG_REG"):
        if not isinstance(fitted_model, LIRFittedModel):
            raise ModelArtifactCompatibilityError(
                f"Loaded model is of type {type(fitted_model)}, expected LIRFittedModel"
            )
        params = metadata.hyperparameters
        if float(params["alpha"]) != fitted_model.fit_metadata.alpha:
            raise ModelArtifactCompatibilityError("Metadata alpha does not match model state")
        if tuple(params["feature_names"]) != fitted_model.fit_metadata.feature_names:
            raise ModelArtifactCompatibilityError("Metadata feature_names do not match model state")
        if tuple(params["pacf_selected_lags"]) != fitted_model.pacf_selected_lags:
            raise ModelArtifactCompatibilityError("Metadata pacf_selected_lags do not match model state")

    elif code_upper == "ARIMA":
        if not isinstance(fitted_model, FittedArimaModel):
            raise ModelArtifactCompatibilityError(
                f"Loaded model is of type {type(fitted_model)}, expected FittedArimaModel"
            )
        params = metadata.hyperparameters
        if tuple(params["order"]) != fitted_model.specification.order:
            raise ModelArtifactCompatibilityError("Metadata order does not match model state")
        if params["trend"] != fitted_model.specification.trend:
            raise ModelArtifactCompatibilityError("Metadata trend does not match model state")

    LOGGER.debug(
        "Successfully verified and loaded model artifact for %s (%s)",
        expected_symbol,
        expected_model_code,
    )
    return fitted_model, metadata


def validate_artifact_against_history(
    metadata: ProductionModelMetadata,
    records: Sequence[OhlcvRecord],
) -> tuple[OhlcvRecord, ...]:
    """Verify that current historical records contain the training boundary without truncation."""
    history = tuple(records)
    require_chronological_records(history)
    if len(history) < metadata.data_row_count:
        raise ModelArtifactCompatibilityError(
            f"History length ({len(history)}) is less than model training row count ({metadata.data_row_count})"
        )
    boundary_record = history[metadata.data_row_count - 1]
    if boundary_record.trading_date != metadata.trained_through:
        raise ModelArtifactCompatibilityError(
            f"History boundary date ({boundary_record.trading_date}) does not match "
            f"model trained_through date ({metadata.trained_through})"
        )
    return history


def load_bundle_for_symbol(
    *,
    bundle_dir: Path,
    symbol: str,
    model_id: str,
    expected_model_version: str | None = None,
) -> tuple[Any, ProductionModelMetadata]:
    """Convenience helper to load a production model artifact for a symbol from a bundle directory."""
    symbol_dir = bundle_dir / symbol
    return load_production_model(
        symbol_directory=symbol_dir,
        expected_symbol=symbol,
        expected_model_code=model_id,
        expected_model_version=expected_model_version,
    )
