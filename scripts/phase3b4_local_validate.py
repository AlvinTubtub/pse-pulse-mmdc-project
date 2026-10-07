#!/usr/bin/env python3
"""Run the approved Phase 3B.4 workflow against an isolated local SQLite clone."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any

from sqlalchemy.engine import make_url

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.config import get_settings
from backend.app.domain.company_universe import get_all_configured_symbols
from backend.app.forecasting.real.artifacts.bundle import (
    ACCEPTANCE_BUNDLE_VERSION,
    verify_bundle,
)
from backend.app.forecasting.real.artifacts.runtime import read_verified_manifest

MANIFEST_SHA256 = "4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454"
BUNDLE_VALIDATION_SHA256 = "3ab0ca422605379c011374c0be8d5cb765c0d74ceb3a5e859d2efc98fca95129"
ACTIVATION_PLAN_SHA256 = "26da93fe8da52cfca4cd026b8a4245c96d745d74eb46cce056680c062390f472"
EVALUATION_RECEIPT_SHA256 = "aa3a6f63cd3ede5c831147d45245f91b2d956416582c9d9bff2b8794fdf1905c"
FAMILIES = ("LAG_REGRESSION", "ARIMA", "LSTM")
INTERNAL_WORKER_ENV = "PHASE3B4_INTERNAL_WORKER"
MUTATING_WORKER_MODES = frozenset(("register", "activate", "first-run", "second-run"))
TRAINING_ENTRYPOINTS = {
    "select_pacf_lags",
    "refit_lir_for_production",
    "refit_arima_for_production",
    "refit_lstm_for_production",
    "select_epoch_count",
    "fit_fixed_epochs",
    "_train_one_epoch",
}


class Phase3B4Error(RuntimeError):
    """Raised when a Phase 3B.4 local-only invariant fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _local_sqlite_path(database_url: str, *, cwd: Path = REPO) -> Path:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or url.host:
        raise Phase3B4Error("Phase 3B.4 currently requires a local SQLite source and validation database")
    if not url.database or url.database == ":memory:":
        raise Phase3B4Error("A file-backed local SQLite database is required for a consistent clone")
    path = Path(url.database).expanduser()
    return (cwd / path).resolve() if not path.is_absolute() else path.resolve()


def _require_local_validation_target(database_url: str, validation_path: Path, repo: Path = REPO) -> None:
    actual = _local_sqlite_path(database_url)
    expected = validation_path.expanduser().resolve()
    try:
        expected.relative_to(repo.resolve())
    except ValueError:
        pass
    else:
        raise Phase3B4Error("Validation database must be outside the Git repository")
    if actual != expected:
        raise Phase3B4Error("DATABASE_URL does not point to the exact isolated Phase 3B.4 validation database")


def _require_execution_confirmations(args: argparse.Namespace, *, environment: str) -> None:
    if environment.lower() == "production":
        raise Phase3B4Error("Phase 3B.4 execution is forbidden in ENVIRONMENT=production")
    if args.confirm_bundle_version != ACCEPTANCE_BUNDLE_VERSION:
        raise Phase3B4Error("--execute requires the exact --confirm-bundle-version")
    if args.confirm_manifest_sha != MANIFEST_SHA256:
        raise Phase3B4Error("--execute requires the exact --confirm-manifest-sha")
    if not args.confirm_local_validation:
        raise Phase3B4Error("--execute requires --confirm-local-validation")


def _trust_anchor_paths() -> dict[str, Path]:
    root = Path.home() / "pse-pulse-production-artifacts"
    return {
        "manifest": root / ACCEPTANCE_BUNDLE_VERSION / "manifest.json",
        "bundle_validation": root / "bundle_validation.json",
        "activation_plan": root / "phase3b3" / ACCEPTANCE_BUNDLE_VERSION / "activation_plan.json",
        "evaluation_receipt": root / "phase3b3" / ACCEPTANCE_BUNDLE_VERSION / "phase3b3_evaluation.json",
    }


def _verify_trust_anchors() -> dict[str, str]:
    expected = {
        "manifest": MANIFEST_SHA256,
        "bundle_validation": BUNDLE_VALIDATION_SHA256,
        "activation_plan": ACTIVATION_PLAN_SHA256,
        "evaluation_receipt": EVALUATION_RECEIPT_SHA256,
    }
    paths = _trust_anchor_paths()
    observed = {name: sha256_file(paths[name]) for name in expected}
    if observed != expected:
        raise Phase3B4Error("One or more frozen Phase 3B trust-anchor hashes changed")
    receipt = json.loads(paths["evaluation_receipt"].read_text(encoding="utf-8"))
    required_receipt_values = {
        "decision": "ELIGIBLE_FOR_ACTIVATION",
        "activation_status": "BUT_NOT_ACTIVATED",
        "bundle_version": ACCEPTANCE_BUNDLE_VERSION,
        "manifest_sha256": MANIFEST_SHA256,
        "boundary_replay_count": 45,
        "reproduction_match_count": 45,
        "current_shadow_count": 45,
        "database_row_deltas": {"Forecast": 0, "ModelArtifact": 0, "PipelineRun": 0},
        "activation_database_preflight": {"canonical_company_count": 15, "runtime_model_metadata_count": 3},
        "verification": {"bundle_version": ACCEPTANCE_BUNDLE_VERSION, "artifact_count": 45, "safe_reload_count": 45},
    }
    if any(receipt.get(key) != value for key, value in required_receipt_values.items()):
        raise Phase3B4Error("The Phase 3B.3 evaluation receipt does not satisfy the accepted activation gate")
    if receipt.get("activation_plan_sha256") not in (None, ACTIVATION_PLAN_SHA256):
        raise Phase3B4Error("The Phase 3B.3 evaluation receipt references a different activation plan")
    return observed


def _source_fingerprint(path: Path) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        result[candidate.name] = sha256_file(candidate) if candidate.is_file() else None
    return result


def _snapshot_sqlite(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"alembic_version", "companies", "daily_prices", "model_metadata", "model_artifacts", "forecasts", "pipeline_runs"}
        if not required.issubset(tables):
            raise Phase3B4Error("SQLite database is missing required application tables")
        count = lambda table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return {
            "schema_revision": connection.execute("SELECT version_num FROM alembic_version").fetchone()[0],
            "counts": {name: count(name) for name in (
                "companies", "daily_prices", "model_metadata", "model_artifacts", "forecasts", "pipeline_runs",
            )},
            "active_companies": [row[0] for row in connection.execute("SELECT symbol FROM companies WHERE is_active=1 ORDER BY symbol")],
            "model_metadata_counts": {row[0]: row[1] for row in connection.execute("SELECT code,COUNT(*) FROM model_metadata GROUP BY code")},
            "history_first": connection.execute("SELECT MIN(trade_date) FROM daily_prices").fetchone()[0],
            "history_last": connection.execute("SELECT MAX(trade_date) FROM daily_prices").fetchone()[0],
            "active_artifact_count": connection.execute("SELECT COUNT(*) FROM model_artifacts WHERE is_active=1").fetchone()[0],
            "candidate_artifact_count": connection.execute(
                "SELECT COUNT(*) FROM model_artifacts WHERE bundle_version=?", (ACCEPTANCE_BUNDLE_VERSION,),
            ).fetchone()[0],
            "active_candidate_count": connection.execute(
                "SELECT COUNT(*) FROM model_artifacts WHERE bundle_version=? AND is_active=1", (ACCEPTANCE_BUNDLE_VERSION,),
            ).fetchone()[0],
            "candidate_forecast_count": connection.execute(
                "SELECT COUNT(*) FROM forecasts f JOIN model_artifacts a ON a.id=f.model_artifact_id "
                "WHERE f.is_demo=0 AND a.bundle_version=?", (ACCEPTANCE_BUNDLE_VERSION,),
            ).fetchone()[0],
        }
    finally:
        connection.close()


def _validate_source_snapshot(snapshot: dict[str, Any]) -> None:
    symbols = sorted(get_all_configured_symbols())
    if snapshot["schema_revision"] not in ("0005_add_model_artifacts_and_forecast_lineage", "0006_model_artifacts_inactive_by_default"):
        raise Phase3B4Error(f"Unexpected source schema revision: {snapshot['schema_revision']}")
    if snapshot["active_companies"] != symbols:
        raise Phase3B4Error("Source database canonical active company universe differs")
    if any(snapshot["model_metadata_counts"].get(family) != 1 for family in FAMILIES):
        raise Phase3B4Error("Source database must contain exactly one metadata row per candidate family")
    if snapshot["history_last"] is None or snapshot["history_last"] < "2026-10-01":
        raise Phase3B4Error("Source OHLCV does not reach the accepted 2026-10-01 training boundary")
    if snapshot["candidate_artifact_count"] or snapshot["active_candidate_count"] or snapshot["candidate_forecast_count"]:
        raise Phase3B4Error("Source database already contains Phase 3B.4 candidate activation state")


def _sqlite_url(path: Path) -> str:
    return "sqlite:///" + str(path.resolve())


def _child_environment(database_url: str, *, activation: bool = False, inference: bool = False) -> dict[str, str]:
    child = os.environ.copy()
    child.update({
        "DATABASE_URL": database_url,
        "DEBUG": "false",
        "ENVIRONMENT": "development",
        "DEMO_MODE": "false",
        "AUTO_CREATE_SCHEMA": "false",
        "MODEL_ARTIFACT_ACTIVATION_ENABLED": "true" if activation else "false",
        "REAL_MODELS_ENABLED": "true" if inference else "false",
    })
    return child


def _run_worker(
    phase: str,
    validation_db: Path,
    *,
    bundle_root: Path,
    evaluation_receipt: Path,
    activation: bool = False,
    inference: bool = False,
) -> dict[str, Any]:
    command = [
        sys.executable, str(Path(__file__).resolve()),
        "--worker-mode", phase,
        "--validation-db", str(validation_db.resolve()),
        "--bundle-root", str(bundle_root.resolve()),
        "--evaluation-receipt", str(evaluation_receipt.resolve()),
    ]
    if phase in MUTATING_WORKER_MODES:
        command.extend((
            "--confirm-bundle-version", ACCEPTANCE_BUNDLE_VERSION,
            "--confirm-manifest-sha", MANIFEST_SHA256,
            "--confirm-local-validation",
        ))
    child_env = _child_environment(_sqlite_url(validation_db), activation=activation, inference=inference)
    child_env[INTERNAL_WORKER_ENV] = "1"
    completed = subprocess.run(
        command,
        cwd=REPO,
        env=child_env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        details = (completed.stdout + "\n" + completed.stderr).strip()[-5000:]
        raise Phase3B4Error(f"Fresh-process phase '{phase}' failed ({completed.returncode}):\n{details}")
    marker = "PHASE3B4_WORKER_JSON:"
    lines = [line[len(marker):] for line in completed.stdout.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise Phase3B4Error(f"Fresh-process phase '{phase}' did not return exactly one result record")
    return json.loads(lines[0])


def _emit_worker_result(payload: dict[str, Any]) -> int:
    print("PHASE3B4_WORKER_JSON:" + json.dumps(payload, sort_keys=True, allow_nan=False))
    return 0


def _lineage_snapshot(db: Any, bundle_version: str) -> list[tuple[Any, ...]]:
    from backend.app.models.model_artifact import ModelArtifact

    return [tuple(getattr(row, key) for key in (
        "company_id", "model_metadata_id", "bundle_version", "artifact_format", "artifact_path",
        "artifact_sha256", "trained_through", "data_row_count", "hyperparameters_json",
        "source_repository", "source_commit", "historical_data_source_repository",
        "historical_data_source_commit", "is_active",
    )) for row in db.query(ModelArtifact).filter_by(bundle_version=bundle_version).order_by(ModelArtifact.id)]


def _assert_worker_target(validation_db: Path, *, activation_worker: bool = False) -> None:
    from backend.app.config import get_settings

    settings = get_settings()
    if settings.ENVIRONMENT.lower() == "production":
        raise Phase3B4Error("Worker refuses ENVIRONMENT=production")
    if settings.MODEL_ARTIFACT_ACTIVATION_ENABLED and not activation_worker:
        raise Phase3B4Error("Unexpected activation permission outside the dedicated activation process")
    if activation_worker and not settings.MODEL_ARTIFACT_ACTIVATION_ENABLED:
        raise Phase3B4Error("Dedicated activation process lacks its process-scoped permission")
    _require_local_validation_target(settings.DATABASE_URL, validation_db)


def _worker(args: argparse.Namespace) -> int:
    if os.environ.get(INTERNAL_WORKER_ENV) != "1":
        raise Phase3B4Error("Worker mode requires the Phase 3B.4 internal worker authorization")
    if args.worker_mode in MUTATING_WORKER_MODES:
        _require_execution_confirmations(args, environment=get_settings().ENVIRONMENT)
    validation_db = args.validation_db.resolve()
    _assert_worker_target(validation_db, activation_worker=args.worker_mode == "activate")
    from backend.app.config import get_settings
    from backend.app.database import SessionLocal, engine
    from backend.app.domain.company_universe import get_all_configured_symbols
    from backend.app.forecasting.real.artifacts.bundle import verify_bundle
    from backend.app.forecasting.real.calendar import PSETradingCalendar
    from backend.app.models.company import Company
    from backend.app.models.forecast import Forecast
    from backend.app.models.model_artifact import ModelArtifact
    from backend.app.models.model_metadata import ModelMetadata
    from backend.app.models.pipeline_run import PipelineRun
    from backend.app.services.model_activation_service import activate_candidate_bundle, register_candidate_bundle
    from backend.app.services.real_forecast_service import RealForecastService

    settings = get_settings()
    bundle_root = args.bundle_root.resolve()
    if args.worker_mode == "register":
        db = SessionLocal()
        try:
            forecasts_before = db.query(Forecast).count()
            runs_before = db.query(PipelineRun).count()
            inserted = register_candidate_bundle(db, bundle_root)
            first_lineage = _lineage_snapshot(db, ACCEPTANCE_BUNDLE_VERSION)
            after_first = {
                "rows": db.query(ModelArtifact).filter_by(bundle_version=ACCEPTANCE_BUNDLE_VERSION).count(),
                "active": db.query(ModelArtifact).filter_by(bundle_version=ACCEPTANCE_BUNDLE_VERSION, is_active=True).count(),
            }
            repeated_inserted = register_candidate_bundle(db, bundle_root)
            second_lineage = _lineage_snapshot(db, ACCEPTANCE_BUNDLE_VERSION)
            if inserted != 45 or repeated_inserted != 0 or after_first != {"rows": 45, "active": 0}:
                raise Phase3B4Error("Candidate registration counts violate the 45 inactive row contract")
            if first_lineage != second_lineage:
                raise Phase3B4Error("Repeated candidate registration changed persisted lineage")
            if db.query(Forecast).count() != forecasts_before or db.query(PipelineRun).count() != runs_before:
                raise Phase3B4Error("Registration wrote Forecast or PipelineRun rows")
            return _emit_worker_result({
                "inserted": inserted,
                "second_registration_inserted": repeated_inserted,
                "candidate_rows": after_first["rows"],
                "active_candidate_rows": after_first["active"],
                "forecast_delta": 0,
                "pipeline_run_delta": 0,
                "lineage_unchanged": True,
            })
        finally:
            db.close()

    if args.worker_mode == "activate":
        if not settings.MODEL_ARTIFACT_ACTIVATION_ENABLED:
            raise Phase3B4Error("Activation worker must receive process-scoped activation permission")
        os.environ["PHASE3B4_ACTIVATION_WORKER"] = "1"
        db = SessionLocal()
        try:
            forecast_count = db.query(Forecast).count()
            run_count = db.query(PipelineRun).count()
            activate_candidate_bundle(
                db,
                bundle_root,
                confirm_bundle_version=args.confirm_bundle_version,
                confirm_manifest_sha256=args.confirm_manifest_sha,
                evaluation_receipt_path=args.evaluation_receipt,
            )
            active = db.query(ModelArtifact).filter_by(bundle_version=ACCEPTANCE_BUNDLE_VERSION, is_active=True).count()
            inactive = db.query(ModelArtifact).filter_by(bundle_version=ACCEPTANCE_BUNDLE_VERSION, is_active=False).count()
            total = db.query(ModelArtifact).filter_by(bundle_version=ACCEPTANCE_BUNDLE_VERSION).count()
            if (total, active, inactive) != (45, 45, 0):
                raise Phase3B4Error("Activation did not leave exactly 45 active candidate rows")
            if db.query(Forecast).count() != forecast_count or db.query(PipelineRun).count() != run_count:
                raise Phase3B4Error("Activation wrote forecast or pipeline audit rows")
            grouped = db.query(ModelArtifact.model_metadata_id).filter_by(bundle_version=ACCEPTANCE_BUNDLE_VERSION, is_active=True).all()
            if len(grouped) != 45:
                raise Phase3B4Error("Activation row cardinality check failed")
            return _emit_worker_result({"candidate_rows": total, "active_candidate_rows": active, "inactive_candidate_rows": inactive, "forecast_delta": 0, "pipeline_run_delta": 0})
        finally:
            db.close()

    if args.worker_mode == "restart-check":
        if settings.MODEL_ARTIFACT_ACTIVATION_ENABLED or settings.REAL_MODELS_ENABLED:
            raise Phase3B4Error("Fresh restart-check process must have both safety switches false")
        verification = verify_bundle(bundle_root)
        with SessionLocal() as db:
            active = db.query(ModelArtifact).filter_by(bundle_version=ACCEPTANCE_BUNDLE_VERSION, is_active=True).count()
            if active != 45 or verification.get("safe_reload_count") != 45:
                raise Phase3B4Error("Activation did not survive restart or bundle did not verify 45/45")
        return _emit_worker_result({"active_candidate_rows": active, "bundle_safe_reload_count": verification["safe_reload_count"], "activation_flag": False, "real_models_flag": False})

    if args.worker_mode in ("dry-run", "first-run", "second-run"):
        if not settings.REAL_MODELS_ENABLED or settings.MODEL_ARTIFACT_ACTIVATION_ENABLED:
            raise Phase3B4Error("Inference process requires REAL_MODELS_ENABLED=true and activation permission=false")
        _install_no_training_guard()
        before = _db_counts(SessionLocal)
        before_rows = _candidate_forecast_rows(SessionLocal, ACCEPTANCE_BUNDLE_VERSION)
        db = SessionLocal()
        try:
            summary = RealForecastService(db).generate_and_persist_forecasts(
                artifacts_root=bundle_root.parent,
                bundle_version=ACCEPTANCE_BUNDLE_VERSION,
                target_symbols=get_all_configured_symbols(),
                model_codes=FAMILIES,
                dry_run=(args.worker_mode == "dry-run"),
            )
        finally:
            db.close()
        after = _db_counts(SessionLocal)
        after_rows = _candidate_forecast_rows(SessionLocal, ACCEPTANCE_BUNDLE_VERSION)
        if args.worker_mode == "dry-run":
            if before != after or before_rows != after_rows or len(summary.items) != 45 or summary.total_forecasts_persisted != 0:
                raise Phase3B4Error("Dry-run inference generated an unexpected count or mutated database state")
            return _emit_worker_result({"companies": summary.total_companies, "prediction_count": len(summary.items), "forecast_delta": 0, "model_artifact_delta": 0, "pipeline_run_delta": 0, "dry_run": True})

        if args.worker_mode == "first-run":
            if len(before_rows) != 0 or len(after_rows) != 45 or summary.total_forecasts_persisted != 45:
                raise Phase3B4Error("First persistent inference did not create exactly 45 forecasts")
            if after["model_artifacts"] != before["model_artifacts"] or after["pipeline_runs"] != before["pipeline_runs"] + 1:
                raise Phase3B4Error("First persistent inference wrote artifacts or unexpected audit rows")
            run_id = summary.run_id
            with SessionLocal() as db:
                run_record = db.query(PipelineRun).filter_by(run_id=run_id).one()
            if run_record.status != "COMPLETED" or run_record.forecasts_generated != 45 or run_record.is_demo_run:
                raise Phase3B4Error("First inference PipelineRun audit row is not completed with 45 forecasts")
            return _emit_worker_result(_validate_persisted_forecasts(SessionLocal, bundle_root, run_id, before, after))

        if len(before_rows) != 45 or len(after_rows) != 45 or before_rows != after_rows:
            raise Phase3B4Error("Second inference changed, duplicated, or removed persisted forecasts")
        if summary.total_forecasts_persisted != 0 or summary.total_forecasts_unchanged != 45:
            raise Phase3B4Error("Second inference did not report 45 unchanged forecasts")
        if after["forecasts"] != before["forecasts"] or after["model_artifacts"] != before["model_artifacts"] or after["pipeline_runs"] != before["pipeline_runs"] + 1:
            raise Phase3B4Error("Second inference database deltas differ from the idempotency contract")
        with SessionLocal() as db:
            run = db.query(PipelineRun).filter_by(run_id=summary.run_id).one()
            if run.status != "COMPLETED" or run.forecasts_generated != 0:
                raise Phase3B4Error("Second inference audit row is not a completed zero-new-forecast run")
        return _emit_worker_result({"new_forecasts": 0, "unchanged_forecasts": 45, "forecast_delta": 0, "model_artifact_delta": 0, "pipeline_run_delta": 1, "unchanged_ids_and_lineage": True})

    if args.worker_mode == "recover-first-run-check":
        if settings.MODEL_ARTIFACT_ACTIVATION_ENABLED or settings.REAL_MODELS_ENABLED:
            raise Phase3B4Error("Read-only recovery check must have both safety switches false")
        after = _db_counts(SessionLocal)
        rows = _candidate_forecast_rows(SessionLocal, ACCEPTANCE_BUNDLE_VERSION)
        if len(rows) != 45 or len({row[4] for row in rows}) != 1:
            raise Phase3B4Error("Interrupted run state does not contain exactly one complete 45-forecast batch")
        pipeline_id = rows[0][4]
        with SessionLocal() as db:
            run = db.query(PipelineRun).filter_by(id=pipeline_id).one()
            if run.status != "COMPLETED" or run.forecasts_generated != 45 or run.is_demo_run:
                raise Phase3B4Error("Recovered first inference run is not a completed 45-forecast run")
            run_id = run.run_id
        before = dict(after)
        before["forecasts"] -= 45
        before["pipeline_runs"] -= 1
        result = _validate_persisted_forecasts(SessionLocal, bundle_root, run_id, before, after)
        result["recovered_after_worker_validation_error"] = True
        return _emit_worker_result(result)

    if args.worker_mode == "api":
        if settings.MODEL_ARTIFACT_ACTIVATION_ENABLED or settings.REAL_MODELS_ENABLED:
            raise Phase3B4Error("Read-only API process must have both safety switches false")
        counts_before = _db_counts(SessionLocal)
        from fastapi.testclient import TestClient
        from backend.app.main import app

        with TestClient(app) as client:
            health = client.get("/health")
            companies = client.get("/api/v1/companies")
            forecasts = client.get("/api/v1/forecasts/latest?limit=200")
            models = client.get("/api/v1/models")
            pipeline = client.get("/api/v1/pipeline/status")
        if any(response.status_code != 200 for response in (health, companies, forecasts, models, pipeline)):
            raise Phase3B4Error("One or more read-only API endpoints failed")
        company_symbols = {item["symbol"] for item in companies.json()}
        if not set(get_all_configured_symbols()).issubset(company_symbols):
            raise Phase3B4Error("Company API did not expose the canonical 15 symbols")
        family_codes = {item["code"] for item in models.json()}
        if not set(FAMILIES).issubset(family_codes):
            raise Phase3B4Error("Model API did not expose all three model families")
        real_api_rows = [item for item in forecasts.json()["forecasts"] if not item["is_demo"]]
        if len(real_api_rows) != 45 or {item["model_code"] for item in real_api_rows} != set(FAMILIES):
            raise Phase3B4Error("Latest forecasts API did not expose all 45 real forecasts and three families")
        pipeline_payload = pipeline.json()
        last_run = pipeline_payload.get("last_run")
        if not last_run or last_run.get("status") != "COMPLETED" or last_run.get("is_demo_run"):
            raise Phase3B4Error("Pipeline API does not show the completed real inference run")
        if _db_counts(SessionLocal) != counts_before:
            raise Phase3B4Error("Read-only API startup changed validation database rows")
        return _emit_worker_result({"health": "PASS", "canonical_companies": len(set(get_all_configured_symbols()) & company_symbols), "real_forecasts_visible": len(real_api_rows), "families": sorted({item["model_code"] for item in real_api_rows}), "pipeline_status": last_run["status"], "activation_flag": False, "real_models_flag": False, "database_delta": 0})

    raise Phase3B4Error(f"Unknown internal worker phase: {args.worker_mode}")


def _install_no_training_guard() -> None:
    import sys as runtime_sys

    def profile(frame: Any, event: str, _arg: Any) -> None:
        module = frame.f_globals.get("__name__") or ""
        if event == "call" and module.startswith("backend.app.forecasting.real.training") and frame.f_code.co_name in TRAINING_ENTRYPOINTS:
            raise Phase3B4Error(f"Training entrypoint reached during inference: {module}.{frame.f_code.co_name}")

    runtime_sys.setprofile(profile)


def _db_counts(session_factory: Any) -> dict[str, int]:
    from backend.app.models.company import Company
    from backend.app.models.price import DailyPrice
    from backend.app.models.forecast import Forecast
    from backend.app.models.model_artifact import ModelArtifact
    from backend.app.models.model_metadata import ModelMetadata
    from backend.app.models.pipeline_run import PipelineRun

    with session_factory() as db:
        return {
            "companies": db.query(Company).count(),
            "daily_prices": db.query(DailyPrice).count(),
            "model_metadata": db.query(ModelMetadata).count(),
            "model_artifacts": db.query(ModelArtifact).count(),
            "forecasts": db.query(Forecast).count(),
            "pipeline_runs": db.query(PipelineRun).count(),
        }


def _candidate_forecast_rows(session_factory: Any, bundle_version: str) -> list[tuple[Any, ...]]:
    from backend.app.models.forecast import Forecast
    from backend.app.models.model_artifact import ModelArtifact

    with session_factory() as db:
        rows = db.query(Forecast).join(ModelArtifact, Forecast.model_artifact_id == ModelArtifact.id).filter(
            Forecast.is_demo.is_(False), ModelArtifact.bundle_version == bundle_version,
        ).order_by(Forecast.id).all()
        return [(
            row.id, row.company_id, row.model_id, row.model_artifact_id, row.pipeline_run_id,
            row.origin_date.isoformat() if row.origin_date else None,
            row.target_date.isoformat(), str(row.predicted_price), str(row.predicted_delta),
        ) for row in rows]


def _validate_persisted_forecasts(session_factory: Any, bundle_root: Path, run_id: str, before: dict[str, int], after: dict[str, int]) -> dict[str, Any]:
    from backend.app.forecasting.real.calendar import PSETradingCalendar
    from backend.app.forecasting.real.history import load_company_ohlcv_history
    from backend.app.models.company import Company
    from backend.app.models.price import DailyPrice
    from backend.app.models.forecast import Forecast
    from backend.app.models.model_artifact import ModelArtifact
    from backend.app.models.model_metadata import ModelMetadata
    from backend.app.models.pipeline_run import PipelineRun

    manifest, digest = read_verified_manifest(bundle_root)
    if digest != MANIFEST_SHA256:
        raise Phase3B4Error("Manifest changed before forecast lineage validation")
    entries = {(entry["symbol"], entry["model_code"]): entry for entry in manifest["entries"]}
    with session_factory() as db:
        run = db.query(PipelineRun).filter_by(run_id=run_id).one()
        company_by_id = {row.id: row for row in db.query(Company).all()}
        metadata_by_id = {row.id: row for row in db.query(ModelMetadata).all()}
        rows = db.query(Forecast).join(ModelArtifact, Forecast.model_artifact_id == ModelArtifact.id).filter(
            Forecast.pipeline_run_id == run.id,
            Forecast.is_demo.is_(False),
            ModelArtifact.bundle_version == ACCEPTANCE_BUNDLE_VERSION,
        ).all()
        if len(rows) != 45:
            raise Phase3B4Error(f"Expected 45 linked real forecasts, found {len(rows)}")
        family_counts: Counter[str] = Counter()
        origins: set[str] = set()
        targets: set[str] = set()
        calendar = PSETradingCalendar()
        for forecast in rows:
            company = company_by_id[forecast.company_id]
            metadata = metadata_by_id[forecast.model_id]
            artifact = db.query(ModelArtifact).filter_by(id=forecast.model_artifact_id).one()
            entry = entries[(company.symbol, metadata.code)]
            metadata_file = json.loads((bundle_root / entry["metadata_relative_path"]).read_text(encoding="utf-8"))
            expected = {
                "bundle_version": ACCEPTANCE_BUNDLE_VERSION,
                "is_active": True,
                "artifact_format": entry["artifact_format"],
                "artifact_path": entry["artifact_relative_path"],
                "artifact_sha256": entry["artifact_sha256"],
                "trained_through": date.fromisoformat(entry["trained_through"]),
                "data_row_count": entry["data_row_count"],
                "source_repository": metadata_file["source_repository"],
                "source_commit": metadata_file["source_commit"],
                "historical_data_source_repository": metadata_file["historical_data_source_repository"],
                "historical_data_source_commit": metadata_file["historical_data_source_commit"],
            }
            if any(getattr(artifact, key) != value for key, value in expected.items()):
                raise Phase3B4Error(f"Persisted forecast lineage does not match manifest for {company.symbol}/{metadata.code}")
            if forecast.model_artifact_id is None or forecast.pipeline_run_id != run.id or forecast.origin_date is None:
                raise Phase3B4Error("Persisted forecast is missing artifact, run, or origin lineage")
            if forecast.is_demo or float(forecast.predicted_price) <= 0:
                raise Phase3B4Error("Persisted forecast is demo or has a non-positive predicted price")
            price, delta = float(forecast.predicted_price), float(forecast.predicted_delta)
            if not math.isfinite(price) or not math.isfinite(delta):
                raise Phase3B4Error("Persisted forecast contains a non-finite value")
            history = load_company_ohlcv_history(db, company.id)
            latest = history[-1]
            if forecast.origin_date != latest.trading_date:
                raise Phase3B4Error("Persisted forecast origin differs from latest canonical OHLCV")
            target = calendar.next_trading_day(latest.trading_date)
            if forecast.target_date != target:
                raise Phase3B4Error("Persisted forecast target differs from PSETradingCalendar")
            origins.add(forecast.origin_date.isoformat())
            targets.add(forecast.target_date.isoformat())
            family_counts[metadata.code] += 1
        if family_counts != Counter({family: 15 for family in FAMILIES}) or len(origins) != 1 or len(targets) != 1:
            raise Phase3B4Error("Forecast family cardinality or shared origin/target validation failed")
        if run.status != "COMPLETED" or run.forecasts_generated != 45 or run.is_demo_run:
            raise Phase3B4Error("Completed inference PipelineRun has invalid status or counts")
    return {
        "companies": 15,
        "forecast_count": 45,
        "family_counts": dict(family_counts),
        "origin_date": next(iter(origins)),
        "target_date": next(iter(targets)),
        "pipeline_run_id": run.id,
        "new_forecast_delta": after["forecasts"] - before["forecasts"],
        "model_artifact_delta": after["model_artifacts"] - before["model_artifacts"],
        "pipeline_run_delta": after["pipeline_runs"] - before["pipeline_runs"],
        "exact_manifest_lineage": True,
    }


def _migrate_clone(validation_db: Path) -> None:
    env = _child_environment(_sqlite_url(validation_db))
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
        cwd=REPO, env=env, text=True, capture_output=True, check=False,
    )
    if completed.returncode:
        raise Phase3B4Error("Alembic failed on the isolated clone:\n" + (completed.stdout + completed.stderr)[-4000:])


def _clone_sqlite_source(source_db: Path, validation_db: Path) -> None:
    validation_db.parent.mkdir(parents=True, exist_ok=True)
    if validation_db.exists():
        raise Phase3B4Error(f"Refusing to overwrite existing validation database: {validation_db}")
    source = sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)
    destination = sqlite3.connect(validation_db)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def _orchestrate(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    _require_execution_confirmations(args, environment=settings.ENVIRONMENT)
    if settings.MODEL_ARTIFACT_ACTIVATION_ENABLED or settings.REAL_MODELS_ENABLED:
        raise Phase3B4Error("Ordinary process safety switches must remain false before Phase 3B.4")
    source_url = os.environ.get("PHASE3B4_SOURCE_DATABASE_URL") or settings.DATABASE_URL
    source_db = _local_sqlite_path(source_url)
    bundle_root = args.bundle_root.resolve()
    evaluation_receipt = args.evaluation_receipt.resolve()
    output_dir = args.validation_dir.expanduser().resolve()
    try:
        output_dir.relative_to(REPO.resolve())
    except ValueError:
        pass
    else:
        raise Phase3B4Error("Phase 3B.4 validation directory must be outside Git")
    validation_db = output_dir / "phase3b4_validation.db"
    receipt_path = output_dir / "phase3b4_activation_receipt.json"
    if receipt_path.exists():
        raise Phase3B4Error("Refusing to overwrite an existing Phase 3B.4 execution receipt")

    anchors = _verify_trust_anchors()
    bundle_pre = verify_bundle(bundle_root)
    manifest, manifest_digest = read_verified_manifest(bundle_root)
    if manifest_digest != MANIFEST_SHA256 or bundle_pre.get("safe_reload_count") != 45:
        raise Phase3B4Error("Frozen bundle pre-verification did not pass 45/45")

    source_before = _source_fingerprint(source_db)
    source_snapshot = _snapshot_sqlite(source_db)
    _validate_source_snapshot(source_snapshot)
    resumed_after_first_persist = validation_db.exists()
    if not resumed_after_first_persist:
        _clone_sqlite_source(source_db, validation_db)
        _migrate_clone(validation_db)
        validation_baseline = _snapshot_sqlite(validation_db)
        _validate_source_snapshot(validation_baseline)
        if validation_baseline["schema_revision"] != "0006_model_artifacts_inactive_by_default":
            raise Phase3B4Error("Isolated validation clone did not reach Alembic head 0006")
        if validation_baseline["counts"] != source_snapshot["counts"]:
            raise Phase3B4Error("Clone/migration changed application row counts before candidate registration")
        registration = _run_worker("register", validation_db, bundle_root=bundle_root, evaluation_receipt=evaluation_receipt)
        activation = _run_worker(
            "activate", validation_db, bundle_root=bundle_root, evaluation_receipt=evaluation_receipt,
            activation=True,
        )
    else:
        # Resume only the exact completed activation + first-inference state left
        # by this driver's post-commit verification import error. Never overwrite
        # or clean an unexpected pre-existing Phase 3B.4 database.
        current = _snapshot_sqlite(validation_db)
        expected_counts = dict(source_snapshot["counts"])
        expected_counts["model_artifacts"] += 45
        expected_counts["forecasts"] += 45
        expected_counts["pipeline_runs"] += 1
        if (
            current["schema_revision"] != "0006_model_artifacts_inactive_by_default"
            or current["counts"] != expected_counts
            or current["candidate_artifact_count"] != 45
            or current["active_candidate_count"] != 45
            or current["candidate_forecast_count"] != 45
        ):
            raise Phase3B4Error("Existing validation database is not the exact resumable post-first-run state")
        validation_baseline = dict(source_snapshot)
        validation_baseline["schema_revision"] = "0006_model_artifacts_inactive_by_default"
        registration = {
            "inserted": 45,
            "second_registration_inserted": 0,
            "candidate_rows": 45,
            "active_candidate_rows": 0,
            "forecast_delta": 0,
            "pipeline_run_delta": 0,
            "lineage_unchanged": True,
            "resumed_from_verified_first_run_state": True,
        }
        activation = {
            "candidate_rows": 45,
            "active_candidate_rows": 45,
            "inactive_candidate_rows": 0,
            "forecast_delta": 0,
            "pipeline_run_delta": 0,
            "resumed_from_verified_first_run_state": True,
        }
    restart = _run_worker("restart-check", validation_db, bundle_root=bundle_root, evaluation_receipt=evaluation_receipt)
    dry_run = _run_worker("dry-run", validation_db, bundle_root=bundle_root, evaluation_receipt=evaluation_receipt, inference=True)
    if resumed_after_first_persist:
        first_run = _run_worker("recover-first-run-check", validation_db, bundle_root=bundle_root, evaluation_receipt=evaluation_receipt)
    else:
        first_run = _run_worker("first-run", validation_db, bundle_root=bundle_root, evaluation_receipt=evaluation_receipt, inference=True)
    second_run = _run_worker("second-run", validation_db, bundle_root=bundle_root, evaluation_receipt=evaluation_receipt, inference=True)
    api = _run_worker("api", validation_db, bundle_root=bundle_root, evaluation_receipt=evaluation_receipt)
    bundle_post = verify_bundle(bundle_root)
    anchors_post = _verify_trust_anchors()
    source_after = _source_fingerprint(source_db)
    if source_after != source_before:
        raise Phase3B4Error("Source database file or SQLite sidecar hashes changed during validation")
    final_db = _snapshot_sqlite(validation_db)
    if final_db["candidate_artifact_count"] != 45 or final_db["active_candidate_count"] != 45 or final_db["candidate_forecast_count"] != 45:
        raise Phase3B4Error("Final validation database counts differ from the Phase 3B.4 target")
    if final_db["counts"]["pipeline_runs"] != validation_baseline["counts"]["pipeline_runs"] + 2:
        raise Phase3B4Error("Expected two new successful real inference PipelineRun rows")
    if bundle_post.get("safe_reload_count") != 45 or anchors_post != anchors:
        raise Phase3B4Error("Frozen bundle or trust anchors changed during local validation")

    return {
        "schema_id": "pse-pulse.local-activation-receipt",
        "schema_version": 1,
        "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "bundle_version": ACCEPTANCE_BUNDLE_VERSION,
        "manifest_sha256": MANIFEST_SHA256,
        "bundle_validation_sha256": BUNDLE_VALIDATION_SHA256,
        "phase3b3_activation_plan_sha256": ACTIVATION_PLAN_SHA256,
        "phase3b3_evaluation_receipt_sha256": EVALUATION_RECEIPT_SHA256,
        "validation_database_type": "isolated local SQLite clone",
        "validation_database_path": str(validation_db),
        "validation_database_sha256": sha256_file(validation_db),
        "source_database_mutated": False,
        "source_database_fingerprint_before": source_before,
        "source_database_fingerprint_after": source_after,
        "source_database_baseline": source_snapshot,
        "validation_database_baseline": validation_baseline,
        "resumed_after_first_persist": resumed_after_first_persist,
        "registration": registration,
        "activation": activation,
        "restart_boundary": restart,
        "dry_run": dry_run,
        "first_persistent_run": first_run,
        "second_run": second_run,
        "api_validation": api,
        "final_candidate_rows": final_db["candidate_artifact_count"],
        "final_active_candidate_rows": final_db["active_candidate_count"],
        "final_non_demo_forecasts": final_db["candidate_forecast_count"],
        "final_row_counts": final_db["counts"],
        "bundle_pre_verification": bundle_pre,
        "bundle_post_verification": bundle_post,
        "normal_activation_flag": False,
        "normal_real_models_flag": False,
        "no_training_entrypoints_reached": True,
        "azure_deployed": False,
        "decision": "LOCAL_PRODUCTION_VALIDATED",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="Print checks and intended local-only actions (default)")
    mode.add_argument("--execute", action="store_true", help="Clone, register, activate, infer, and validate locally")
    parser.add_argument("--confirm-bundle-version")
    parser.add_argument("--confirm-manifest-sha")
    parser.add_argument("--confirm-local-validation", action="store_true")
    parser.add_argument("--validation-dir", type=Path, default=Path.home() / "pse-pulse-production-artifacts" / "phase3b4" / ACCEPTANCE_BUNDLE_VERSION)
    parser.add_argument("--bundle-root", type=Path, default=Path.home() / "pse-pulse-production-artifacts" / ACCEPTANCE_BUNDLE_VERSION)
    parser.add_argument("--evaluation-receipt", type=Path, default=Path.home() / "pse-pulse-production-artifacts" / "phase3b3" / ACCEPTANCE_BUNDLE_VERSION / "phase3b3_evaluation.json")
    parser.add_argument("--worker-mode", choices=("register", "activate", "restart-check", "dry-run", "first-run", "second-run", "recover-first-run-check", "api"), help=argparse.SUPPRESS)
    parser.add_argument("--validation-db", type=Path, help=argparse.SUPPRESS)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.worker_mode:
            if args.validation_db is None:
                raise Phase3B4Error("Internal worker requires a validation database path")
            return _worker(args)
        if not args.execute:
            settings = get_settings()
            source_url = os.environ.get("PHASE3B4_SOURCE_DATABASE_URL") or settings.DATABASE_URL
            source = _local_sqlite_path(source_url)
            target = args.validation_dir.expanduser().resolve() / "phase3b4_validation.db"
            print(json.dumps({
                "mode": "PLAN ONLY",
                "source_database": str(source),
                "source_database_type": "local SQLite",
                "validation_database": str(target),
                "validation_database_outside_repository": REPO.resolve() not in target.parents,
                "frozen_trust_anchors": _verify_trust_anchors(),
                "bundle_verification": verify_bundle(args.bundle_root),
                "execute_requires": {
                    "--confirm-bundle-version": ACCEPTANCE_BUNDLE_VERSION,
                    "--confirm-manifest-sha": MANIFEST_SHA256,
                    "--confirm-local-validation": True,
                },
                "no_database_changes": True,
            }, indent=2, sort_keys=True))
            return 0
        result = _orchestrate(args)
        receipt_path = args.validation_dir.expanduser().resolve() / "phase3b4_activation_receipt.json"
        receipt_path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"receipt_path": str(receipt_path), "receipt_sha256": sha256_file(receipt_path), "decision": result["decision"]}, indent=2))
        return 0
    except Exception as exc:
        parser.exit(1, f"PHASE 3B.4 FAILED: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
