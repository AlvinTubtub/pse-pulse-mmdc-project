"""Artifact persistence with cryptographic SHA-256 hashing and companion JSON metadata."""

from datetime import date, datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import joblib

from backend.app.forecasting.real.artifacts.schema import (
    MODEL_ARTIFACT_SCHEMA_ID,
    MODEL_ARTIFACT_SCHEMA_VERSION,
    MODEL_IMPLEMENTATION_VERSION,
    OFFICIAL_SOURCE_COMMIT,
    OFFICIAL_SOURCE_REPOSITORY,
    ProductionModelMetadata,
)
from backend.app.forecasting.real.calendar import manila_now

LOGGER = logging.getLogger(__name__)


def compute_artifact_sha256(path: Path) -> str:
    """Compute the SHA-256 cryptographic checksum of a file in 1 MB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def persist_model_artifact(
    *,
    output_directory: Path,
    symbol: str,
    model_code: str,
    model_version: str,
    fitted_model: Any,
    hyperparameters: dict[str, Any],
    trained_through: date,
    data_row_count: int,
    created_at: datetime | None = None,
    source_repository: str = OFFICIAL_SOURCE_REPOSITORY,
    source_commit: str = OFFICIAL_SOURCE_COMMIT,
    historical_data_source_repository: str = OFFICIAL_SOURCE_REPOSITORY,
    historical_data_source_commit: str = OFFICIAL_SOURCE_COMMIT,
) -> tuple[ProductionModelMetadata, Path, Path]:
    """Persist a fitted model binary via joblib and write companion JSON metadata.

    Returns (metadata, model_path, metadata_path).
    """
    directory = output_directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)

    artifact_filename = f"{model_code.lower()}.joblib"
    metadata_filename = f"{model_code.lower()}.metadata.json"

    model_path = directory / artifact_filename
    metadata_path = directory / metadata_filename

    # 1. Serialize binary model via joblib
    joblib.dump(fitted_model, model_path)

    # 2. Compute SHA-256 checksum over the written binary
    artifact_sha = compute_artifact_sha256(model_path)

    # 3. Construct metadata
    timestamp = created_at if created_at is not None else manila_now()
    metadata = ProductionModelMetadata(
        symbol=symbol,
        model_code=model_code,
        model_version=model_version,
        trained_through=trained_through,
        data_row_count=data_row_count,
        hyperparameters=hyperparameters,
        created_at=timestamp,
        artifact_format="joblib",
        artifact_filename=artifact_filename,
        artifact_sha256=artifact_sha,
        schema_id=MODEL_ARTIFACT_SCHEMA_ID,
        schema_version=MODEL_ARTIFACT_SCHEMA_VERSION,
        implementation_version=MODEL_IMPLEMENTATION_VERSION,
        source_repository=source_repository,
        source_commit=source_commit,
        historical_data_source_repository=historical_data_source_repository,
        historical_data_source_commit=historical_data_source_commit,
    )

    # 4. Write companion JSON metadata
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata.as_dict(), f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")

    LOGGER.info(
        "Persisted model artifact symbol=%s model=%s path=%s sha256=%s",
        symbol,
        model_code,
        model_path,
        artifact_sha,
    )
    return metadata, model_path, metadata_path
