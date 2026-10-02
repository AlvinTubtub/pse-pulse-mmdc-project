"""Real model artifact management, checksum verification, and safe loading package."""

from backend.app.forecasting.real.artifacts.schema import (
    MODEL_ARTIFACT_SCHEMA_ID,
    MODEL_ARTIFACT_SCHEMA_VERSION,
    MODEL_IMPLEMENTATION_VERSION,
    ModelArtifactCompatibilityError,
    ProductionModelMetadata,
)
from backend.app.forecasting.real.artifacts.writer import (
    compute_artifact_sha256,
    persist_model_artifact,
)
from backend.app.forecasting.real.artifacts.loader import (
    load_bundle_for_symbol,
    load_production_model,
    validate_artifact_against_history,
    validate_model_artifact_metadata,
)

__all__ = [
    "MODEL_ARTIFACT_SCHEMA_ID",
    "MODEL_ARTIFACT_SCHEMA_VERSION",
    "MODEL_IMPLEMENTATION_VERSION",
    "ModelArtifactCompatibilityError",
    "ProductionModelMetadata",
    "compute_artifact_sha256",
    "persist_model_artifact",
    "load_bundle_for_symbol",
    "load_production_model",
    "validate_artifact_against_history",
    "validate_model_artifact_metadata",
]
