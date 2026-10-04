"""Fail-closed candidate registration and explicit atomic artifact activation."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import uuid

from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.domain.company_universe import get_all_configured_symbols
from backend.app.forecasting.real.artifacts.bundle import ACCEPTANCE_BUNDLE_VERSION, verify_bundle
from backend.app.forecasting.real.artifacts.runtime import read_verified_manifest
from backend.app.models.company import Company
from backend.app.models.model_artifact import ModelArtifact
from backend.app.models.model_metadata import ModelMetadata

FAMILIES = ("LAG_REGRESSION", "ARIMA", "LSTM")
ACCEPTED_MANIFEST_SHA256 = "4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454"


class ModelActivationError(RuntimeError):
    """Raised when candidate registration or activation fails closed."""


def _preflight(db: Session) -> tuple[dict[str, Company], dict[str, ModelMetadata]]:
    expected_symbols = set(get_all_configured_symbols())
    companies = {
        row.symbol: row
        for row in db.query(Company)
        .filter(Company.is_active.is_(True), Company.symbol.in_(expected_symbols))
        .all()
    }
    if set(companies) != expected_symbols:
        raise ModelActivationError("Database is missing one or more active canonical companies")
    model_rows = db.query(ModelMetadata).filter(ModelMetadata.code.in_(FAMILIES)).all()
    by_code: dict[str, list[ModelMetadata]] = {code: [] for code in FAMILIES}
    for row in model_rows:
        by_code[row.code].append(row)
    if any(len(by_code[code]) != 1 for code in FAMILIES):
        raise ModelActivationError("Database must contain exactly one ModelMetadata row for each required family")
    return companies, {code: rows[0] for code, rows in by_code.items()}


def activation_database_preflight(db: Session) -> dict[str, int]:
    """Read-only activation prerequisites used by the eligibility evaluator."""
    companies, models = _preflight(db)
    return {"canonical_company_count": len(companies), "runtime_model_metadata_count": len(models)}


def register_candidate_bundle(db: Session, bundle_root: Path) -> int:
    """Atomically register the verified inventory as inactive; never forecasts or activates."""
    try:
        inserted = _register_candidate_bundle(db, bundle_root)
        db.commit()
        return inserted
    except Exception:
        db.rollback()
        raise


def _register_candidate_bundle(db: Session, bundle_root: Path) -> int:
    """Perform candidate registration within the public operation's transaction."""
    verification = verify_bundle(bundle_root)
    if verification.get("artifact_count") != 45 or verification.get("safe_reload_count") != 45:
        raise ModelActivationError("Full candidate bundle verification did not pass 45/45")
    manifest, digest = read_verified_manifest(bundle_root)
    if digest != ACCEPTED_MANIFEST_SHA256:
        raise ModelActivationError("Manifest SHA-256 differs from the accepted frozen bundle")
    companies, models = _preflight(db)
    registered = 0
    for entry in manifest["entries"]:
        company = companies[entry["symbol"]]
        model = models[entry["model_code"]]
        relative_path = entry["artifact_relative_path"]
        metadata_path = Path(bundle_root) / entry["metadata_relative_path"]
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        candidate = {
            "artifact_format": entry["artifact_format"],
            "artifact_path": relative_path,
            "artifact_sha256": entry["artifact_sha256"],
            "trained_through": date.fromisoformat(entry["trained_through"]),
            "data_row_count": entry["data_row_count"],
            "hyperparameters_json": json.dumps(metadata["hyperparameters"], sort_keys=True, separators=(",", ":")),
            "source_repository": metadata["source_repository"],
            "source_commit": metadata["source_commit"],
            "historical_data_source_repository": metadata["historical_data_source_repository"],
            "historical_data_source_commit": metadata["historical_data_source_commit"],
        }
        row = db.query(ModelArtifact).filter_by(
            company_id=company.id,
            model_metadata_id=model.id,
            bundle_version=ACCEPTANCE_BUNDLE_VERSION,
        ).one_or_none()
        if row is None:
            db.add(ModelArtifact(
                id=str(uuid.uuid4()), company_id=company.id, model_metadata_id=model.id,
                bundle_version=ACCEPTANCE_BUNDLE_VERSION, is_active=False, **candidate,
            ))
            registered += 1
            continue
        if any(getattr(row, key) != value for key, value in candidate.items()):
            raise ModelActivationError(f"Existing candidate lineage conflicts for {entry['symbol']}/{entry['model_code']}")
        if row.is_active:
            raise ModelActivationError("Candidate row must remain inactive during registration")
    db.flush()
    rows = db.query(ModelArtifact).filter_by(bundle_version=ACCEPTANCE_BUNDLE_VERSION).all()
    if len(rows) != 45:
        raise ModelActivationError(f"Expected exactly 45 candidate rows after registration, found {len(rows)}")
    return registered


def activate_candidate_bundle(
    db: Session,
    bundle_root: Path,
    *,
    confirm_bundle_version: str,
    confirm_manifest_sha256: str,
    evaluation_receipt_path: Path | None = None,
) -> None:
    """Atomically switch to the exact candidate; caller controls transaction ownership."""
    settings = get_settings()
    if not settings.MODEL_ARTIFACT_ACTIVATION_ENABLED:
        raise ModelActivationError("MODEL_ARTIFACT_ACTIVATION_ENABLED is false")
    if confirm_bundle_version != ACCEPTANCE_BUNDLE_VERSION:
        raise ModelActivationError("Bundle version confirmation mismatch")
    verification = verify_bundle(bundle_root)
    manifest, digest = read_verified_manifest(bundle_root)
    if digest != ACCEPTED_MANIFEST_SHA256 or digest != confirm_manifest_sha256:
        raise ModelActivationError("Manifest SHA-256 confirmation mismatch")
    receipt_path = evaluation_receipt_path or (
        Path(bundle_root).resolve().parent / "phase3b3" / confirm_bundle_version / "phase3b3_evaluation.json"
    )
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelActivationError("A valid Phase 3B.3 evaluation receipt is required before activation") from exc
    if (
        receipt.get("decision") != "ELIGIBLE_FOR_ACTIVATION"
        or receipt.get("bundle_version") != confirm_bundle_version
        or receipt.get("manifest_sha256") != ACCEPTED_MANIFEST_SHA256
        or receipt.get("verification") != {"bundle_version": confirm_bundle_version, "artifact_count": 45, "safe_reload_count": 45}
        or receipt.get("boundary_replay_count") != 45
        or receipt.get("reproduction_match_count") != 45
        or receipt.get("current_shadow_count") != 45
        or receipt.get("database_row_deltas") != {"Forecast": 0, "ModelArtifact": 0, "PipelineRun": 0}
        or receipt.get("activation_feature_enabled") is not False
        or receipt.get("real_models_enabled") is not False
        or receipt.get("activation_database_preflight") != {"canonical_company_count": 15, "runtime_model_metadata_count": 3}
        or receipt.get("activation_plan_validation") != "PASS"
        or receipt.get("frozen_bundle_unchanged_after_evaluation") is not True
    ):
        raise ModelActivationError("Phase 3B.3 evaluation receipt does not establish activation eligibility")
    if verification.get("artifact_count") != 45 or verification.get("safe_reload_count") != 45:
        raise ModelActivationError("Candidate bundle is not verified 45/45")
    companies, models = _preflight(db)
    entries = manifest["entries"]
    candidate_rows = db.query(ModelArtifact).filter_by(bundle_version=confirm_bundle_version).all()
    expected_keys = {(companies[e["symbol"]].id, models[e["model_code"]].id) for e in entries}
    actual_keys = {(r.company_id, r.model_metadata_id) for r in candidate_rows}
    if len(candidate_rows) != 45 or actual_keys != expected_keys or any(r.is_active for r in candidate_rows):
        raise ModelActivationError("Candidate rows are missing, extra, duplicated, or already active")
    rows_by_key = {(row.company_id, row.model_metadata_id): row for row in candidate_rows}
    for entry in entries:
        company = companies[entry["symbol"]]
        model = models[entry["model_code"]]
        metadata = json.loads((Path(bundle_root) / entry["metadata_relative_path"]).read_text(encoding="utf-8"))
        row = rows_by_key[(company.id, model.id)]
        expected = {
            "artifact_format": entry["artifact_format"],
            "artifact_path": entry["artifact_relative_path"],
            "artifact_sha256": entry["artifact_sha256"],
            "trained_through": date.fromisoformat(entry["trained_through"]),
            "data_row_count": entry["data_row_count"],
            "hyperparameters_json": json.dumps(metadata["hyperparameters"], sort_keys=True, separators=(",", ":")),
            "source_repository": metadata["source_repository"],
            "source_commit": metadata["source_commit"],
            "historical_data_source_repository": metadata["historical_data_source_repository"],
            "historical_data_source_commit": metadata["historical_data_source_commit"],
        }
        if any(getattr(row, key) != value for key, value in expected.items()):
            raise ModelActivationError(f"Candidate DB lineage differs from verified bundle for {entry['symbol']}/{entry['model_code']}")
    try:
        for company_id, model_id in expected_keys:
            db.query(ModelArtifact).filter(
                ModelArtifact.company_id == company_id,
                ModelArtifact.model_metadata_id == model_id,
                ModelArtifact.is_active.is_(True),
                ModelArtifact.bundle_version != confirm_bundle_version,
            ).update({ModelArtifact.is_active: False}, synchronize_session=False)
        db.query(ModelArtifact).filter_by(bundle_version=confirm_bundle_version).update(
            {ModelArtifact.is_active: True}, synchronize_session=False
        )
        db.flush()
        active = db.query(ModelArtifact).filter_by(bundle_version=confirm_bundle_version, is_active=True).count()
        if active != 45:
            raise ModelActivationError(f"Activation invariant failed: expected 45 active rows, found {active}")
        db.commit()
    except Exception:
        db.rollback()
        raise
