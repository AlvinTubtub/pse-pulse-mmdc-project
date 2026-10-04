"""Per-company authoritative bindings for serialized Phase 3A model families."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backend.app.forecasting.real.artifacts.loader import (
    load_production_model,
    validate_model_artifact_metadata,
)
from backend.app.forecasting.real.artifacts.schema import (
    MODEL_ARTIFACT_SCHEMA_ID,
    MODEL_ARTIFACT_SCHEMA_VERSION,
    MODEL_IMPLEMENTATION_VERSION,
    ModelArtifactCompatibilityError,
    ProductionModelMetadata,
)
from backend.app.forecasting.real.artifacts.writer import persist_model_artifact
from backend.app.forecasting.real.config import DEFAULT_LAG_REGRESSION_CONFIG
from backend.app.forecasting.real.models.arima import ConvergenceStatus, FittedArimaModel
from backend.app.forecasting.real.selections import (
    OFFICIAL_REPOSITORY,
    SELECTION_SOURCE_COMMIT,
    AuthoritativeModelSelection,
    SelectionProvenance,
    load_selection_catalog,
)
from backend.app.forecasting.real.training.refit_lir import LIRFittedModel

AUTHORITATIVE_REGIME = "AUTHORITATIVE"


def _selection_for(symbol: str) -> AuthoritativeModelSelection:
    try:
        return load_selection_catalog()[symbol]
    except KeyError as exc:
        raise ValueError(f"No authoritative selection exists for {symbol}") from exc


def persist_authoritative_lir(
    *,
    output_directory: Path,
    symbol: str,
    model_version: str,
    fitted: LIRFittedModel,
    trained_through,
    data_row_count: int,
    formal_selected_features_evidence: tuple[str, ...],
    selection_provenance: SelectionProvenance,
):
    selection = _selection_for(symbol)
    if fitted.fit_metadata.alpha != selection.lir_alpha:
        raise ValueError(f"LIR alpha for {symbol} differs from authoritative selection")
    if selection_provenance != selection.provenance:
        raise ValueError(f"LIR selection provenance for {symbol} differs from catalog")
    metadata, artifact_path, metadata_path = persist_model_artifact(
        output_directory=output_directory,
        symbol=symbol,
        model_code="LAG_REGRESSION",
        model_version=model_version,
        fitted_model=fitted,
        hyperparameters={
            "alpha": selection.lir_alpha,
            "feature_names": list(fitted.fit_metadata.feature_names),
            "pacf_selected_lags": list(fitted.pacf_selected_lags),
            "feature_count": len(fitted.fit_metadata.feature_names),
            "formal_selected_features_evidence": list(formal_selected_features_evidence),
            "feature_config": asdict(DEFAULT_LAG_REGRESSION_CONFIG.features),
            "pacf_method": "ywmle",
            "hyperparameter_regime": AUTHORITATIVE_REGIME,
            "test_only_smoke": False,
            "selection_provenance": selection.provenance.as_dict(),
        },
        trained_through=trained_through,
        data_row_count=data_row_count,
        source_repository=OFFICIAL_REPOSITORY,
        source_commit=SELECTION_SOURCE_COMMIT,
        historical_data_source_repository=OFFICIAL_REPOSITORY,
        historical_data_source_commit=SELECTION_SOURCE_COMMIT,
    )
    return metadata, artifact_path, metadata_path


def persist_authoritative_arima(
    *,
    output_directory: Path,
    symbol: str,
    model_version: str,
    fitted: FittedArimaModel,
    trained_through,
    data_row_count: int,
    selection_provenance: SelectionProvenance,
):
    selection = _selection_for(symbol)
    if fitted.specification != selection.arima:
        raise ValueError(f"ARIMA specification for {symbol} differs from authoritative selection")
    if fitted.convergence is not ConvergenceStatus.CONFIRMED_CONVERGED:
        raise ValueError(f"ARIMA for {symbol} lacks confirmed convergence")
    if selection_provenance != selection.provenance:
        raise ValueError(f"ARIMA selection provenance for {symbol} differs from catalog")
    fit_evidence = fitted.fit_metadata()
    metadata, artifact_path, metadata_path = persist_model_artifact(
        output_directory=output_directory,
        symbol=symbol,
        model_code="ARIMA",
        model_version=model_version,
        fitted_model=fitted,
        hyperparameters={
            **selection.arima.as_dict(),
            "convergence_status": fitted.convergence.value,
            "fit_evidence": fit_evidence,
            "hyperparameter_regime": AUTHORITATIVE_REGIME,
            "test_only_smoke": False,
            "selection_provenance": selection.provenance.as_dict(),
        },
        trained_through=trained_through,
        data_row_count=data_row_count,
        source_repository=OFFICIAL_REPOSITORY,
        source_commit=SELECTION_SOURCE_COMMIT,
        historical_data_source_repository=OFFICIAL_REPOSITORY,
        historical_data_source_commit=SELECTION_SOURCE_COMMIT,
    )
    return metadata, artifact_path, metadata_path


def _validate_authoritative_metadata(
    payload: dict[str, Any],
    *,
    symbol: str,
    model_code: str,
    model_version: str,
    trained_through,
    data_row_count: int,
) -> tuple[ProductionModelMetadata, AuthoritativeModelSelection]:
    try:
        selection = _selection_for(symbol)
    except ValueError as exc:
        raise ModelArtifactCompatibilityError(str(exc)) from exc
    metadata = validate_model_artifact_metadata(
        payload,
        expected_symbol=symbol,
        expected_model_code=model_code,
        expected_model_version=model_version,
    )
    if metadata.schema_id != MODEL_ARTIFACT_SCHEMA_ID or metadata.schema_version != MODEL_ARTIFACT_SCHEMA_VERSION:
        raise ModelArtifactCompatibilityError("Unsupported authoritative model schema")
    if metadata.implementation_version != MODEL_IMPLEMENTATION_VERSION:
        raise ModelArtifactCompatibilityError("Unsupported authoritative implementation version")
    if metadata.trained_through != trained_through or metadata.data_row_count != data_row_count:
        raise ModelArtifactCompatibilityError("Authoritative artifact history boundary mismatch")
    if payload.get("source_repository") != OFFICIAL_REPOSITORY or payload.get("source_commit") != SELECTION_SOURCE_COMMIT:
        raise ModelArtifactCompatibilityError("Authoritative model source provenance mismatch")
    if payload.get("historical_data_source_repository") != OFFICIAL_REPOSITORY or payload.get("historical_data_source_commit") != SELECTION_SOURCE_COMMIT:
        raise ModelArtifactCompatibilityError("Authoritative historical source provenance mismatch")
    hp = metadata.hyperparameters
    if hp.get("hyperparameter_regime") != AUTHORITATIVE_REGIME or hp.get("test_only_smoke") is not False:
        raise ModelArtifactCompatibilityError("Artifact is not an authoritative production candidate")
    if hp.get("selection_provenance") != selection.provenance.as_dict():
        raise ModelArtifactCompatibilityError("Authoritative selection provenance mismatch")
    if model_code == "LAG_REGRESSION":
        if hp.get("alpha") != selection.lir_alpha:
            raise ModelArtifactCompatibilityError("LIR alpha differs from authoritative selection")
        if not isinstance(hp.get("feature_count"), int) or hp["feature_count"] != len(hp.get("feature_names", [])):
            raise ModelArtifactCompatibilityError("LIR fitted feature-count evidence is invalid")
    elif model_code == "ARIMA":
        if tuple(hp.get("order", ())) != selection.arima.order or hp.get("trend") != selection.arima.trend:
            raise ModelArtifactCompatibilityError("ARIMA specification differs from authoritative selection")
        if hp.get("convergence_status") != ConvergenceStatus.CONFIRMED_CONVERGED.value:
            raise ModelArtifactCompatibilityError("ARIMA convergence is not confirmed")
        evidence = hp.get("fit_evidence")
        if not isinstance(evidence, dict) or evidence.get("convergence_status") != ConvergenceStatus.CONFIRMED_CONVERGED.value:
            raise ModelArtifactCompatibilityError("ARIMA fit evidence does not confirm convergence")
    return metadata, selection


def load_authoritative_model(
    *,
    symbol_directory: Path,
    expected_symbol: str,
    expected_model_code: str,
    expected_model_version: str,
    trained_through,
    data_row_count: int,
):
    """Bind common and company-specific metadata before the SHA-checked safe loader."""
    metadata_path = Path(symbol_directory) / f"{expected_model_code.lower()}.metadata.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelArtifactCompatibilityError("Cannot read authoritative artifact metadata") from exc
    if not isinstance(payload, dict):
        raise ModelArtifactCompatibilityError("Authoritative metadata must be a JSON object")
    metadata, selection = _validate_authoritative_metadata(
        payload,
        symbol=expected_symbol,
        model_code=expected_model_code,
        model_version=expected_model_version,
        trained_through=trained_through,
        data_row_count=data_row_count,
    )
    model, loaded_metadata = load_production_model(
        symbol_directory=symbol_directory,
        expected_symbol=expected_symbol,
        expected_model_code=expected_model_code,
        expected_model_version=expected_model_version,
    )
    # Confirm the file validated before SHA verification is the metadata returned after loading.
    if loaded_metadata != metadata:
        raise ModelArtifactCompatibilityError("Authoritative metadata changed during safe loading")
    if expected_model_code == "LAG_REGRESSION" and model.fit_metadata.alpha != selection.lir_alpha:
        raise ModelArtifactCompatibilityError("Loaded LIR alpha differs from authoritative selection")
    if expected_model_code == "ARIMA":
        if model.specification != selection.arima or model.convergence is not ConvergenceStatus.CONFIRMED_CONVERGED:
            raise ModelArtifactCompatibilityError("Loaded ARIMA state differs from authoritative selection")
    return model, loaded_metadata
