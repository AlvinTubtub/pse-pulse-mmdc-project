"""Non-persistent boundary replay and current-history shadow evaluation."""

from __future__ import annotations

from collections import Counter
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any

from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.domain.company_universe import get_all_configured_symbols
from backend.app.forecasting.real.artifacts.bundle import ACCEPTANCE_BUNDLE_VERSION, verify_bundle
from backend.app.forecasting.real.artifacts.runtime import load_runtime_artifact, read_verified_manifest
from backend.app.forecasting.real.calendar import PSETradingCalendar
from backend.app.forecasting.real.history import load_company_ohlcv_history
from backend.app.forecasting.real.inference.predictor import predict_with_production_model
from backend.app.models.company import Company
from backend.app.models.forecast import Forecast
from backend.app.models.model_artifact import ModelArtifact
from backend.app.models.pipeline_run import PipelineRun
from backend.app.services.model_activation_service import activation_database_preflight

BOUNDARY = date(2026, 10, 1)
TARGET = date(2026, 10, 2)


class GateEvaluationError(RuntimeError):
    """Evaluation evidence is missing or an operational gate failed."""


def _counts(db: Session) -> dict[str, int]:
    return {
        "Forecast": db.query(Forecast).count(),
        "ModelArtifact": db.query(ModelArtifact).count(),
        "PipelineRun": db.query(PipelineRun).count(),
    }


def validate_phase3b2_evidence(path: Path) -> tuple[list[dict[str, Any]], str]:
    if not path.is_file():
        raise GateEvaluationError(f"Required Phase 3B.2 evidence is missing: {path}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateEvaluationError("Phase 3B.2 bundle_validation.json is malformed") from exc
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or len(results) != 45:
        raise GateEvaluationError("Phase 3B.2 evidence must contain exactly 45 inference records")
    expected = {(symbol, family) for symbol in get_all_configured_symbols() for family in ("LAG_REGRESSION", "ARIMA", "LSTM")}
    actual: set[tuple[str, str]] = set()
    for row in results:
        if not isinstance(row, dict):
            raise GateEvaluationError("Phase 3B.2 evidence contains a non-object inference record")
        key = (row.get("symbol"), row.get("model_code"))
        if key not in expected or key in actual:
            raise GateEvaluationError(f"Unexpected or duplicate Phase 3B.2 evidence key: {key}")
        actual.add(key)
        if row.get("origin_date") != BOUNDARY.isoformat() or row.get("target_date") != TARGET.isoformat() or row.get("safe_reload_passed") is not True:
            raise GateEvaluationError(f"Invalid Phase 3B.2 evidence boundary or reload flag for {key}")
        for field in ("predicted_delta", "predicted_close", "origin_close"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise GateEvaluationError(f"Invalid numeric {field} in Phase 3B.2 evidence for {key}")
    if actual != expected:
        raise GateEvaluationError("Phase 3B.2 evidence does not cover all 15 symbols and 3 model families")
    return results, digest


def evaluate_bundle(db: Session, bundle_root: Path, evidence_path: Path) -> dict[str, Any]:
    """Run complete bundle verification, boundary replay and current shadow inference."""
    settings = get_settings()
    if settings.REAL_MODELS_ENABLED or settings.MODEL_ARTIFACT_ACTIVATION_ENABLED:
        raise GateEvaluationError("Both REAL_MODELS_ENABLED and MODEL_ARTIFACT_ACTIVATION_ENABLED must remain false")
    before = _counts(db)
    metadata_preflight = activation_database_preflight(db)
    started = time.perf_counter()
    verification = verify_bundle(bundle_root)
    verify_seconds = time.perf_counter() - started
    if verification != {"bundle_version": ACCEPTANCE_BUNDLE_VERSION, "artifact_count": 45, "safe_reload_count": 45}:
        raise GateEvaluationError("Frozen candidate bundle verification was not 45/45")
    manifest, manifest_sha = read_verified_manifest(bundle_root)
    expected_sha = "4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454"
    if manifest_sha != expected_sha:
        raise GateEvaluationError("Frozen candidate manifest SHA-256 differs from approved identity")
    accepted, evidence_sha = validate_phase3b2_evidence(evidence_path)
    accepted_by_key = {(row["symbol"], row["model_code"]): row for row in accepted}
    symbols = tuple(get_all_configured_symbols())
    calendar = PSETradingCalendar()
    replay_start = time.perf_counter()
    replay: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    family_seconds: Counter[str] = Counter()
    boundary_secs = 0.0
    current_secs = 0.0
    for symbol in symbols:
        company = db.query(Company).filter(Company.symbol == symbol, Company.is_active.is_(True)).one_or_none()
        if company is None:
            raise GateEvaluationError(f"Canonical active company is missing: {symbol}")
        full_history = load_company_ohlcv_history(db, company.id)
        if not any(record.trading_date == BOUNDARY for record in full_history):
            raise GateEvaluationError(f"History does not contain frozen training boundary for {symbol}")
        boundary_history = tuple(record for record in full_history if record.trading_date <= BOUNDARY)
        if not boundary_history or boundary_history[-1].trading_date != BOUNDARY:
            raise GateEvaluationError(f"Boundary history is not available for {symbol}")
        if calendar.next_trading_day(BOUNDARY) != TARGET:
            raise GateEvaluationError("PSETradingCalendar did not resolve the accepted target session")
        for family in ("LAG_REGRESSION", "ARIMA", "LSTM"):
            artifact = load_runtime_artifact(
                bundle_root=bundle_root, symbol=symbol, model_code=family,
                expected_version=ACCEPTANCE_BUNDLE_VERSION,
                expected_manifest_sha256=expected_sha,
            )
            tick = time.perf_counter()
            prediction = predict_with_production_model(
                fitted_model=artifact.model, metadata=artifact.metadata, records=boundary_history
            )
            elapsed = time.perf_counter() - tick
            boundary_secs += elapsed
            family_seconds[family] += elapsed
            expected = accepted_by_key[(symbol, family)]
            actual_close = boundary_history[-1].close
            delta_match = math.isclose(prediction.predicted_delta, expected["predicted_delta"], rel_tol=1e-10, abs_tol=1e-8)
            close_match = math.isclose(prediction.predicted_close, expected["predicted_close"], rel_tol=1e-10, abs_tol=1e-8)
            replay.append({
                "symbol": symbol, "model_code": family,
                "origin_date": BOUNDARY.isoformat(), "target_date": TARGET.isoformat(),
                "predicted_delta": prediction.predicted_delta, "predicted_close": prediction.predicted_close,
                "accepted_delta_match": delta_match, "accepted_close_match": close_match,
            })
            if not (delta_match and close_match and math.isclose(actual_close, expected["origin_close"], rel_tol=1e-10, abs_tol=1e-8)):
                raise GateEvaluationError(f"Boundary replay differs from accepted evidence for {symbol}/{family}")
    boundary_total = time.perf_counter() - replay_start
    if len(replay) != 45:
        raise GateEvaluationError("Boundary replay did not produce 45 results")
    current_start = time.perf_counter()
    for symbol in symbols:
        company = db.query(Company).filter(Company.symbol == symbol, Company.is_active.is_(True)).one()
        history = load_company_ohlcv_history(db, company.id)
        for family in ("LAG_REGRESSION", "ARIMA", "LSTM"):
            artifact = load_runtime_artifact(
                bundle_root=bundle_root, symbol=symbol, model_code=family,
                expected_version=ACCEPTANCE_BUNDLE_VERSION,
                expected_manifest_sha256=expected_sha,
            )
            tick = time.perf_counter()
            prediction = predict_with_production_model(
                fitted_model=artifact.model, metadata=artifact.metadata, records=history
            )
            elapsed = time.perf_counter() - tick
            current_secs += elapsed
            family_seconds[family] += elapsed
            origin = history[-1]
            target = calendar.next_trading_day(origin.trading_date)
            if not math.isfinite(prediction.predicted_delta) or not math.isfinite(prediction.predicted_close) or prediction.predicted_close <= 0:
                raise GateEvaluationError(f"Invalid current-history prediction for {symbol}/{family}")
            current.append({
                "symbol": symbol, "model_code": family,
                "origin_date": origin.trading_date.isoformat(), "target_date": target.isoformat(),
                "predicted_delta": prediction.predicted_delta, "predicted_close": prediction.predicted_close,
                "safe_load_passed": True,
            })
    current_total = time.perf_counter() - current_start
    after = _counts(db)
    deltas = {key: after[key] - before[key] for key in before}
    if deltas != {"Forecast": 0, "ModelArtifact": 0, "PipelineRun": 0}:
        raise GateEvaluationError(f"Evaluation mutated database row counts: {deltas}")
    return {
        "bundle_version": manifest["bundle_version"], "manifest_sha256": manifest_sha,
        "phase3b2_validation_sha256": evidence_sha,
        "dependency_boundary_status": "PASS",
        "activation_database_preflight": metadata_preflight,
        "activation_feature_enabled": settings.MODEL_ARTIFACT_ACTIVATION_ENABLED,
        "real_models_enabled": settings.REAL_MODELS_ENABLED,
        "verification": verification,
        "boundary_replay_count": len(replay), "reproduction_match_count": sum(r["accepted_delta_match"] and r["accepted_close_match"] for r in replay),
        "current_shadow_count": len(current),
        "database_counts_before": before, "database_counts_after": after, "database_row_deltas": deltas,
        "results": {"boundary_replay": replay, "current_shadow": current},
        "timings_seconds": {
            "bundle_verification": verify_seconds, "boundary_replay_total": boundary_total,
            "boundary_inference": boundary_secs, "current_shadow_total": current_total,
            "current_inference": current_secs,
            "inference_by_family": dict(family_seconds),
        },
    }
