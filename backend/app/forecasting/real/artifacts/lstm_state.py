"""Safe state-dict artifact persistence for explicitly trained LSTM models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import tempfile
from typing import Any

import torch

from backend.app.forecasting.real.artifacts.schema import (
    MODEL_ARTIFACT_SCHEMA_ID,
    MODEL_ARTIFACT_SCHEMA_VERSION,
    MODEL_IMPLEMENTATION_VERSION,
    ModelArtifactCompatibilityError,
)
from backend.app.forecasting.real.artifacts.writer import compute_artifact_sha256
from backend.app.forecasting.real.calendar import manila_now
from backend.app.forecasting.real.config import LstmSpecification
from backend.app.forecasting.real.models.lstm import (
    DeltaScaler,
    FittedLstmModel,
    UnivariateDeltaLSTM,
    validate_model_state,
)
from backend.app.forecasting.real.selections import (
    OFFICIAL_REPOSITORY,
    SELECTION_SOURCE_COMMIT,
    SelectionCatalogError,
    SelectionProvenance,
    load_selection_catalog,
)

LSTM_ARTIFACT_FORMAT = "pytorch_state_dict"
LSTM_ARTIFACT_EXTENSION = ".pt"
LSTM_MODEL_CODE = "LSTM"


@dataclass(frozen=True, slots=True)
class LoadedLstmArtifact:
    model: FittedLstmModel
    metadata: Mapping[str, Any]
    artifact_path: Path
    metadata_path: Path


def persist_lstm_state_artifact(
    *,
    output_directory: Path,
    symbol: str,
    model_version: str,
    fitted: FittedLstmModel,
    data_row_count: int,
    trained_through: date,
    formal_selected_epoch_count: int,
    selection_provenance: SelectionProvenance,
    source_commit: str = SELECTION_SOURCE_COMMIT,
    historical_data_source_commit: str = SELECTION_SOURCE_COMMIT,
) -> tuple[Path, Path, dict[str, Any]]:
    """Persist CPU tensors only, then write v1-compatible companion metadata."""
    import torch

    try:
        authoritative = load_selection_catalog()[symbol]
    except (SelectionCatalogError, KeyError) as exc:
        raise ValueError(f"No authoritative LSTM selection for {symbol}") from exc
    if fitted.specification != authoritative.lstm:
        raise ValueError(f"LSTM specification for {symbol} differs from its authoritative selection")
    if formal_selected_epoch_count != authoritative.formal_lstm_selected_epoch_count:
        raise ValueError(f"Formal LSTM epoch evidence for {symbol} differs from its authoritative selection")
    if fitted.seed != authoritative.provenance.final_seed:
        raise ValueError("Authoritative production LSTM artifacts must use the selected final seed")
    if selection_provenance != authoritative.provenance:
        raise ValueError(f"Selection provenance for {symbol} differs from the authoritative selection")
    if data_row_count < 2 or fitted.training_size < 1:
        raise ValueError("LSTM artifact training boundaries must be positive")
    validate_model_state(fitted)
    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    artifact_path = root / "lstm.pt"
    metadata_path = root / "lstm.metadata.json"
    checkpoint = {
        "schema_id": MODEL_ARTIFACT_SCHEMA_ID,
        "schema_version": MODEL_ARTIFACT_SCHEMA_VERSION,
        "specification": fitted.specification.as_dict(),
        "selected_epoch_count": fitted.epoch_count,
        "seed": fitted.seed,
        "training_size": fitted.training_size,
        "scaler": fitted.scaler.state_dict(),
        "model_state_dict": fitted.cpu_state_dict(),
    }
    with tempfile.NamedTemporaryFile(
        dir=root, prefix=".lstm-", suffix=".tmp", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        torch.save(checkpoint, temporary_path)
        temporary_path.replace(artifact_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    digest = compute_artifact_sha256(artifact_path)
    hyperparameters: dict[str, Any] = {
        **fitted.specification.as_dict(),
        "selected_epoch_count": fitted.epoch_count,
        "formal_selected_epoch_count": formal_selected_epoch_count,
        "production_selected_epoch_count": fitted.epoch_count,
        "seed": fitted.seed,
        "training_size": fitted.training_size,
        "scaler": fitted.scaler.state_dict(),
        "input_features": ["historical_close_delta"],
        "target": "next_day_close_delta",
        "selection_provenance": selection_provenance.as_dict(),
    }
    metadata: dict[str, Any] = {
        "schema_id": MODEL_ARTIFACT_SCHEMA_ID,
        "schema_version": MODEL_ARTIFACT_SCHEMA_VERSION,
        "implementation_version": MODEL_IMPLEMENTATION_VERSION,
        "symbol": symbol,
        "model_code": LSTM_MODEL_CODE,
        "model_version": model_version,
        "trained_through": trained_through.isoformat(),
        "data_row_count": data_row_count,
        "hyperparameters": hyperparameters,
        "created_at": manila_now().isoformat(),
        "artifact_format": LSTM_ARTIFACT_FORMAT,
        "artifact_filename": artifact_path.name,
        "artifact_sha256": digest,
        "source_repository": OFFICIAL_REPOSITORY,
        "source_commit": source_commit,
        "historical_data_source_repository": OFFICIAL_REPOSITORY,
        "historical_data_source_commit": historical_data_source_commit,
        **selection_provenance.as_dict(),
    }
    temporary_metadata = metadata_path.with_name(".lstm.metadata.tmp")
    temporary_metadata.write_text(
        json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary_metadata.replace(metadata_path)
    return artifact_path, metadata_path, metadata


def _require_sha(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ModelArtifactCompatibilityError("Invalid LSTM artifact SHA-256")
    return value


def _metadata_specification(payload: Mapping[str, Any]) -> LstmSpecification:
    hyperparameters = payload.get("hyperparameters")
    if not isinstance(hyperparameters, Mapping):
        raise ModelArtifactCompatibilityError("Missing LSTM hyperparameters")
    try:
        lookback = hyperparameters["lookback"]
        hidden_size = hyperparameters["hidden_size"]
        batch_size = hyperparameters["batch_size"]
        learning_rate = hyperparameters["learning_rate"]
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (lookback, hidden_size, batch_size)
        ):
            raise ValueError("LSTM integer parameters must be positive integers")
        if (
            isinstance(learning_rate, bool)
            or not isinstance(learning_rate, (int, float))
            or not math.isfinite(learning_rate)
            or learning_rate <= 0
        ):
            raise ValueError("LSTM learning rate must be finite and positive")
        return LstmSpecification(
            lookback=lookback,
            hidden_size=hidden_size,
            learning_rate=float(learning_rate),
            batch_size=batch_size,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelArtifactCompatibilityError("Invalid LSTM hyperparameters") from exc


def load_lstm_state_artifact(
    *,
    symbol_directory: Path,
    expected_symbol: str,
    expected_model_version: str,
    expected_trained_through: date | None = None,
    expected_data_row_count: int | None = None,
) -> LoadedLstmArtifact:
    """Validate identity, format, path, SHA, and history before safe torch.load."""
    directory = Path(symbol_directory).resolve()
    if not directory.is_dir():
        raise ModelArtifactCompatibilityError("LSTM artifact directory is missing")
    metadata_path = directory / "lstm.metadata.json"
    if not metadata_path.is_file():
        raise ModelArtifactCompatibilityError("LSTM metadata file is missing")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelArtifactCompatibilityError("LSTM metadata is unreadable") from exc
    if not isinstance(metadata, Mapping):
        raise ModelArtifactCompatibilityError("LSTM metadata must be a mapping")
    if metadata.get("schema_id") != MODEL_ARTIFACT_SCHEMA_ID:
        raise ModelArtifactCompatibilityError("LSTM metadata schema_id mismatch")
    if metadata.get("schema_version") != MODEL_ARTIFACT_SCHEMA_VERSION:
        raise ModelArtifactCompatibilityError("LSTM metadata schema_version mismatch")
    if metadata.get("implementation_version") != MODEL_IMPLEMENTATION_VERSION:
        raise ModelArtifactCompatibilityError("LSTM implementation version mismatch")
    if metadata.get("symbol") != expected_symbol:
        raise ModelArtifactCompatibilityError("LSTM symbol mismatch")
    if metadata.get("model_code") != LSTM_MODEL_CODE:
        raise ModelArtifactCompatibilityError("LSTM model family mismatch")
    if metadata.get("model_version") != expected_model_version:
        raise ModelArtifactCompatibilityError("LSTM model version mismatch")
    if metadata.get("source_repository") != OFFICIAL_REPOSITORY:
        raise ModelArtifactCompatibilityError("LSTM model source repository mismatch")
    if metadata.get("source_commit") != SELECTION_SOURCE_COMMIT:
        raise ModelArtifactCompatibilityError("LSTM model source commit mismatch")
    if metadata.get("historical_data_source_repository") != OFFICIAL_REPOSITORY:
        raise ModelArtifactCompatibilityError("LSTM historical source repository mismatch")
    if metadata.get("historical_data_source_commit") != SELECTION_SOURCE_COMMIT:
        raise ModelArtifactCompatibilityError("LSTM historical source commit mismatch")
    try:
        authoritative = load_selection_catalog()[expected_symbol]
    except (SelectionCatalogError, KeyError) as exc:
        raise ModelArtifactCompatibilityError(
            f"No authoritative LSTM selection for {expected_symbol}"
        ) from exc
    expected_selection = authoritative.provenance.as_dict()
    if any(metadata.get(key) != value for key, value in expected_selection.items()):
        raise ModelArtifactCompatibilityError("LSTM formal selection provenance mismatch")
    if metadata.get("artifact_format") != LSTM_ARTIFACT_FORMAT:
        raise ModelArtifactCompatibilityError("LSTM artifact format mismatch")
    filename = metadata.get("artifact_filename")
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or filename != f"lstm{LSTM_ARTIFACT_EXTENSION}"
        or "/" in filename
        or "\\" in filename
    ):
        raise ModelArtifactCompatibilityError("Unsafe LSTM artifact filename")
    artifact_path = (directory / filename).resolve()
    if artifact_path.parent != directory or not artifact_path.is_file():
        raise ModelArtifactCompatibilityError("LSTM artifact is missing or unsafe")
    digest = _require_sha(metadata.get("artifact_sha256"))
    # Critical security boundary: no torch import/deserialization before this equality.
    if compute_artifact_sha256(artifact_path) != digest:
        raise ModelArtifactCompatibilityError("LSTM artifact checksum mismatch")
    try:
        trained_through = date.fromisoformat(str(metadata["trained_through"]))
        row_count = metadata["data_row_count"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelArtifactCompatibilityError("Invalid LSTM training boundary") from exc
    if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 2:
        raise ModelArtifactCompatibilityError("Invalid LSTM data_row_count")
    if expected_trained_through is not None and trained_through != expected_trained_through:
        raise ModelArtifactCompatibilityError("LSTM training date boundary mismatch")
    if expected_data_row_count is not None and row_count != expected_data_row_count:
        raise ModelArtifactCompatibilityError("LSTM training row boundary mismatch")
    spec = _metadata_specification(metadata)
    hyperparameters = metadata["hyperparameters"]
    if spec != authoritative.lstm:
        raise ModelArtifactCompatibilityError("LSTM specification differs from authoritative selection")
    required = {
        "selected_epoch_count",
        "production_selected_epoch_count",
        "formal_selected_epoch_count",
        "seed",
        "training_size",
        "scaler",
        "selection_provenance",
    }
    if not required <= set(hyperparameters):
        raise ModelArtifactCompatibilityError("Missing required LSTM hyperparameters")
    try:
        formal_epochs = hyperparameters["formal_selected_epoch_count"]
        epoch_count = hyperparameters["selected_epoch_count"]
        production_epochs = hyperparameters["production_selected_epoch_count"]
        seed = hyperparameters["seed"]
        training_size = hyperparameters["training_size"]
    except KeyError as exc:
        raise ModelArtifactCompatibilityError("Missing LSTM refit metadata") from exc
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in (formal_epochs, epoch_count, production_epochs, training_size)):
        raise ModelArtifactCompatibilityError("Invalid LSTM epoch or training size")
    if formal_epochs > 100:
        raise ModelArtifactCompatibilityError("Formal LSTM epoch evidence exceeds the declared limit")
    if formal_epochs != authoritative.formal_lstm_selected_epoch_count:
        raise ModelArtifactCompatibilityError("Formal LSTM epoch evidence differs from authoritative selection")
    if hyperparameters.get("selection_provenance") != authoritative.provenance.as_dict():
        raise ModelArtifactCompatibilityError("Nested LSTM selection provenance mismatch")
    if epoch_count != production_epochs or seed != authoritative.provenance.final_seed:
        raise ModelArtifactCompatibilityError("Invalid LSTM production refit provenance")
    if training_size != row_count - 1 - spec.lookback:
        raise ModelArtifactCompatibilityError("LSTM sequence training size does not match history")

    try:
        checkpoint = torch.load(artifact_path, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise ModelArtifactCompatibilityError("Cannot load verified LSTM checkpoint") from exc
    if not isinstance(checkpoint, Mapping):
        raise ModelArtifactCompatibilityError("LSTM checkpoint must be mapping-like")
    if checkpoint.get("schema_id") != MODEL_ARTIFACT_SCHEMA_ID:
        raise ModelArtifactCompatibilityError("LSTM checkpoint schema_id mismatch")
    if checkpoint.get("schema_version") != MODEL_ARTIFACT_SCHEMA_VERSION:
        raise ModelArtifactCompatibilityError("LSTM checkpoint schema_version mismatch")
    if checkpoint.get("specification") != spec.as_dict():
        raise ModelArtifactCompatibilityError("LSTM checkpoint specification mismatch")
    if checkpoint.get("selected_epoch_count") != epoch_count:
        raise ModelArtifactCompatibilityError("LSTM checkpoint epoch mismatch")
    if checkpoint.get("seed") != seed:
        raise ModelArtifactCompatibilityError("LSTM checkpoint seed mismatch")
    if checkpoint.get("training_size") != training_size:
        raise ModelArtifactCompatibilityError("LSTM checkpoint training size mismatch")
    scaler_payload = checkpoint.get("scaler")
    if not isinstance(scaler_payload, Mapping):
        raise ModelArtifactCompatibilityError("Invalid LSTM scaler state")
    try:
        scaler = DeltaScaler(
            mean=float(scaler_payload["mean"]),
            scale=float(scaler_payload["scale"]),
            observations=int(scaler_payload["observations"]),
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ModelArtifactCompatibilityError("Invalid LSTM scaler state") from exc
    if (
        not math.isfinite(scaler.mean)
        or not math.isfinite(scaler.scale)
        or scaler.scale <= 0
        or scaler.observations < 1
        or scaler.observations > row_count
        or scaler.observations != row_count - 1
    ):
        raise ModelArtifactCompatibilityError("LSTM scaler values are out of range")
    if hyperparameters.get("scaler") != scaler.state_dict():
        raise ModelArtifactCompatibilityError("LSTM metadata scaler mismatch")
    state_dict = checkpoint.get("model_state_dict")
    if not isinstance(state_dict, Mapping):
        raise ModelArtifactCompatibilityError("LSTM state_dict must be mapping-like")
    if any(not isinstance(tensor, torch.Tensor) or not torch.isfinite(tensor).all() for tensor in state_dict.values()):
        raise ModelArtifactCompatibilityError("LSTM state_dict contains invalid tensors")
    network = UnivariateDeltaLSTM(spec.hidden_size)
    try:
        network.load_state_dict(state_dict, strict=True)
    except (RuntimeError, TypeError) as exc:
        raise ModelArtifactCompatibilityError("LSTM state_dict keys or shapes mismatch") from exc
    model = FittedLstmModel(
        network=network,
        scaler=scaler,
        specification=spec,
        epoch_count=epoch_count,
        seed=seed,
        training_size=training_size,
    )
    validate_model_state(model)
    return LoadedLstmArtifact(model, metadata, artifact_path, metadata_path)
