"""Artifact schema definitions and metadata validation for real production models."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from backend.app.forecasting.real.config import ModelId

MODEL_ARTIFACT_SCHEMA_ID = "pse-pulse.production-model"
MODEL_ARTIFACT_SCHEMA_VERSION = 1
MODEL_IMPLEMENTATION_VERSION = "pse-pulse-v1"

OFFICIAL_SOURCE_REPOSITORY = "https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git"
OFFICIAL_SOURCE_COMMIT = "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1"


class ModelArtifactCompatibilityError(ValueError):
    """Raised when an artifact fails schema, checksum, path, or compatibility validation."""


@dataclass(frozen=True, slots=True)
class ProductionModelMetadata:
    """Immutable metadata record accompanying a serialized model binary."""

    symbol: str
    model_code: str
    model_version: str
    trained_through: date
    data_row_count: int
    hyperparameters: dict[str, Any]
    created_at: datetime
    artifact_format: str
    artifact_filename: str
    artifact_sha256: str
    schema_id: str = MODEL_ARTIFACT_SCHEMA_ID
    schema_version: int = MODEL_ARTIFACT_SCHEMA_VERSION
    implementation_version: str = MODEL_IMPLEMENTATION_VERSION
    source_repository: str = OFFICIAL_SOURCE_REPOSITORY
    source_commit: str = OFFICIAL_SOURCE_COMMIT
    historical_data_source_repository: str = OFFICIAL_SOURCE_REPOSITORY
    historical_data_source_commit: str = OFFICIAL_SOURCE_COMMIT

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "implementation_version": self.implementation_version,
            "symbol": self.symbol,
            "model_code": self.model_code,
            "model_version": self.model_version,
            "trained_through": self.trained_through.isoformat(),
            "data_row_count": self.data_row_count,
            "hyperparameters": self.hyperparameters,
            "created_at": self.created_at.isoformat(),
            "artifact_format": self.artifact_format,
            "artifact_filename": self.artifact_filename,
            "artifact_sha256": self.artifact_sha256,
            "source_repository": self.source_repository,
            "source_commit": self.source_commit,
            "historical_data_source_repository": self.historical_data_source_repository,
            "historical_data_source_commit": self.historical_data_source_commit,
        }
