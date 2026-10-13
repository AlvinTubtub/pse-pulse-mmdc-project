"""Strict production EOD orchestration; never falls back to demo data or models."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import sys

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database import SessionLocal
from backend.app.production_inputs import (
    ApprovedCalendar,
    ProductionInputError as ProductionRunError,
    verify_calendar_manifest,
    verify_source_approval_index,
    verify_source_manifest,
    verify_source_manifest_record,
    validate_bundle_coverage,
    validate_forecast_outcomes,
)
from backend.app.forecasting.real.artifacts.runtime import (
    read_verified_artifact_metadata,
    read_verified_manifest,
)
from backend.app.models.company import Company
from backend.app.models.forecast import Forecast
from backend.app.models.market_data_import import MarketDataImport
from backend.app.models.model_artifact import ModelArtifact
from backend.app.models.model_metadata import ModelMetadata
from backend.app.models.pipeline_run import PipelineRun
from backend.app.models.price import DailyPrice
from backend.app.models.production_session import ProductionSession
from backend.app.services.real_forecast_service import RealForecastService
from backend.pipeline.ingest.eod_ingest import EODIngestionService
from backend.pipeline.persistence.db_saver import DatabaseSaver
from backend.pipeline.validation.data_validator import DataValidator

logger = logging.getLogger("pse_pulse_production_eod")
MODEL_CODES = ("LAG_REGRESSION", "ARIMA", "LSTM")
PRODUCTION_SESSION_LOCK_NAMESPACE = 0x50534550


def _lock_production_session_date(db: Session, trade_date: date) -> None:
    """Serialize EOD attempts for one session date on PostgreSQL."""
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :session_date)"),
        {
            "namespace": PRODUCTION_SESSION_LOCK_NAMESPACE,
            "session_date": trade_date.toordinal(),
        },
    )


def _lock_finalization_claim(db: Session, trade_date: date, pipeline_run_id: int) -> ProductionSession:
    """Lock and verify the durable owner before finalizing a production date."""
    _lock_production_session_date(db, trade_date)
    row = (db.query(ProductionSession)
           .filter(ProductionSession.trade_date == trade_date)
           .populate_existing()
           .with_for_update()
           .one_or_none())
    if row is None or row.pipeline_run_id != pipeline_run_id:
        raise ProductionRunError("The durable production-session claim changed before finalization.")
    if row.status not in {"RUNNING", "COMPLETED"}:
        raise ProductionRunError("The durable production-session claim is not eligible for finalization.")
    return row


def validate_production_settings(settings) -> None:
    if settings.ENVIRONMENT.lower() != "production":
        raise ProductionRunError("Strict production runner requires ENVIRONMENT=production.")
    if settings.DEBUG or settings.DEMO_MODE or settings.AUTO_CREATE_SCHEMA:
        raise ProductionRunError("Debug, demo mode, and automatic schema creation must all be disabled.")
    if settings.MODEL_ARTIFACT_ACTIVATION_ENABLED:
        raise ProductionRunError("The production runner never activates model artifacts.")
    if not settings.REAL_MODELS_ENABLED:
        raise ProductionRunError("REAL_MODELS_ENABLED is false; production inference is fail-closed.")
    if settings.PROCESS_ROLE != "production-eod":
        raise ProductionRunError("Production inference is allowed only in the dedicated EOD process.")


def validate_approved_models(
    db: Session, artifacts_root: Path, bundle_version: str
) -> tuple[list[Company], str, dict[tuple[str, str], ModelArtifact]]:
    bundle = Path(artifacts_root) / bundle_version
    try:
        manifest, manifest_sha = read_verified_manifest(bundle, expected_version=bundle_version)
    except Exception as exc:
        raise ProductionRunError("Approved model bundle is missing or failed integrity validation.") from exc
    companies = db.query(Company).filter(Company.is_active.is_(True)).order_by(Company.symbol.asc()).all()
    if not companies:
        raise ProductionRunError("No active companies are registered.")
    metadata_rows = {row.code: row for row in db.query(ModelMetadata).filter(ModelMetadata.code.in_(MODEL_CODES)).all()}
    if set(metadata_rows) != set(MODEL_CODES):
        raise ProductionRunError("Approved model metadata is incomplete.")
    try:
        validate_bundle_coverage(manifest.get("entries", []), {company.symbol for company in companies}, MODEL_CODES)
    except ProductionRunError:
        raise
    approved_artifacts: dict[tuple[str, str], ModelArtifact] = {}
    for company in companies:
        for code in MODEL_CODES:
            artifacts = db.query(ModelArtifact).filter(
                ModelArtifact.company_id == company.id,
                ModelArtifact.model_metadata_id == metadata_rows[code].id,
                ModelArtifact.is_active.is_(True),
            ).all()
            if len(artifacts) != 1 or artifacts[0].bundle_version != bundle_version:
                raise ProductionRunError("Each company/model must have exactly one previously approved active artifact.")
            approved_artifacts[(company.symbol.upper(), code)] = artifacts[0]
    return companies, manifest_sha, approved_artifacts


def _set_session(
    db: Session,
    trade_date: date,
    status: str,
    calendar_sha: str,
    *,
    source_sha: str | None = None,
    source_manifest_sha: str | None = None,
    source_url: str | None = None,
    source_reviewer: str | None = None,
    market_data_import_id: int | None = None,
    model_bundle_version: str | None = None,
    model_manifest_sha256: str | None = None,
    pipeline_run_id: int | None = None,
    message: str | None = None,
    commit: bool = True,
) -> ProductionSession:
    row = db.query(ProductionSession).filter(ProductionSession.trade_date == trade_date).one_or_none()
    if row is None:
        row = ProductionSession(trade_date=trade_date, status=status, calendar_sha256=calendar_sha)
        db.add(row)
    row.status = status
    row.calendar_sha256 = calendar_sha
    if source_sha is not None:
        row.source_sha256 = source_sha
    if source_manifest_sha is not None:
        row.source_manifest_sha256 = source_manifest_sha
    if source_url is not None:
        row.source_url = source_url
    if source_reviewer is not None:
        row.source_reviewer = source_reviewer
    if market_data_import_id is not None:
        row.market_data_import_id = market_data_import_id
    if model_bundle_version is not None:
        row.model_bundle_version = model_bundle_version
    if model_manifest_sha256 is not None:
        row.model_manifest_sha256 = model_manifest_sha256
    if pipeline_run_id is not None:
        row.pipeline_run_id = pipeline_run_id
    row.message = message
    row.updated_at = datetime.now(timezone.utc)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def _find_source(source_dir: Path, trade_date: date) -> Path | None:
    candidates = [source_dir / f"{trade_date.isoformat()}{suffix}" for suffix in (".pdf", ".txt")]
    existing = [item for item in candidates if item.exists()]
    if len(existing) > 1:
        raise ProductionRunError("Multiple candidate source files exist for the requested session.")
    return existing[0] if existing else None


def _validate_retry_authorization(
    existing: ProductionSession | None,
    retry_failed: bool,
    source_file: Path | None,
    source_manifest: Path | None,
) -> None:
    """Require an explicit exact-date retry and a staged approval pair."""
    if existing is not None and existing.status == "FAILED" and not retry_failed:
        raise ProductionRunError(
            "A failed production session requires an explicit owner-authorized retry."
        )
    if retry_failed and (existing is None or existing.status != "FAILED"):
        raise ProductionRunError("Explicit retry is valid only for an existing FAILED session.")
    if retry_failed and (
        source_file is None or source_manifest is None
        or not source_file.is_file() or not source_manifest.is_file()
    ):
        raise ProductionRunError(
            "Explicit retry requires the exact staged source and its approved manifest."
        )


def _verify_idempotent_import(
    db: Session, source_sha: str, trade_date: date, symbols: set[str]
) -> tuple[int, int] | None:
    records = db.query(MarketDataImport).filter(
        MarketDataImport.sha256 == source_sha,
        MarketDataImport.status == "COMPLETED",
    ).order_by(MarketDataImport.imported_at.asc()).all()
    if not records:
        return None
    if len(records) != 1:
        raise ProductionRunError("Source import lineage is ambiguous; exactly one completed import is required.")
    record = records[0]
    if record.trade_date != trade_date:
        raise ProductionRunError("Previously imported source hash is associated with another trade date.")
    from backend.app.models.price import DailyPrice
    have_prices = {
        symbol for (symbol,) in db.query(Company.symbol).join(DailyPrice, DailyPrice.company_id == Company.id)
        .filter(Company.is_active.is_(True), DailyPrice.trade_date == trade_date).all()
    }
    if have_prices != symbols:
        raise ProductionRunError("Previously imported source has incomplete persisted price coverage.")
    return record.records_inserted + record.records_updated + record.records_unchanged, record.id


def _ingest_verified_source(
    db: Session, source: Path, trade_date: date, symbols: set[str], ingestion: EODIngestionService
) -> tuple[int, str, int]:
    quotes, source_sha = ingestion.ingest_from_file(source, target_date=trade_date, force=False, db=None)
    if not quotes or any(item.trade_date != trade_date for item in quotes):
        raise ProductionRunError("Parsed source is empty or contains a mismatched trading date.")
    valid, invalid = DataValidator().validate_dataset(quotes, target_date=trade_date)
    invalid_tracked = {str(item.get("symbol", "")).strip().upper() for item in invalid} & symbols
    valid_symbols = {item.symbol.strip().upper() for item in valid}
    if invalid_tracked or not symbols.issubset(valid_symbols):
        raise ProductionRunError("Official source failed tracked-symbol validation or coverage.")
    saver = DatabaseSaver(db)
    summary = saver.persist_daily_prices(
        valid,
        sha256_hash=source_sha,
        source_filename=source.name,
        dry_run=False,
        commit=False,
        records_seen=len(quotes),
        records_rejected=len(invalid),
    )
    if summary.records_tracked <= 0:
        db.rollback()
        raise ProductionRunError("Source contained no tracked market rows.")
    saver.record_market_data_import(summary=summary, commit=False)
    imports = db.query(MarketDataImport).filter(
        MarketDataImport.sha256 == source_sha,
        MarketDataImport.trade_date == trade_date,
        MarketDataImport.status == "COMPLETED",
    ).all()
    if len(imports) != 1:
        raise ProductionRunError("Verified source did not produce exactly one completed import record.")
    return summary.records_inserted + summary.records_updated + summary.records_unchanged, source_sha, imports[0].id


def _validate_persisted_forecasts(
    db: Session,
    run: PipelineRun,
    expected_pairs: set[tuple[str, str]],
    origin_date: date,
    target_date: date,
    *,
    approved_artifacts: dict[tuple[str, str], ModelArtifact] | None = None,
    bundle_entries: dict[tuple[str, str], dict] | None = None,
    bundle_version: str | None = None,
    bundle_root: Path | None = None,
) -> int:
    rows = (
        db.query(Forecast, Company, ModelMetadata)
        .join(Company, Forecast.company_id == Company.id)
        .join(ModelMetadata, Forecast.model_id == ModelMetadata.id)
        .filter(Forecast.pipeline_run_id == run.id)
        .all()
    )
    pairs = [(company.symbol.upper(), metadata.code.upper()) for _, company, metadata in rows]
    if len(rows) != len(expected_pairs) or set(pairs) != expected_pairs or len(set(pairs)) != len(pairs):
        raise ProductionRunError("Persisted forecasts do not contain exactly one required company/model pair per run.")
    for forecast, company, metadata in rows:
        key = (company.symbol.upper(), metadata.code.upper())
        if forecast.is_demo:
            raise ProductionRunError("Synthetic/demo forecast rows were found in the production run.")
        if forecast.origin_date != origin_date or forecast.target_date != target_date:
            raise ProductionRunError("Persisted forecast origin or target differs from the approved calendar.")
        try:
            predicted = float(forecast.predicted_price)
            delta = float(forecast.predicted_delta)
            lower = None if forecast.lower_bound is None else float(forecast.lower_bound)
            upper = None if forecast.upper_bound is None else float(forecast.upper_bound)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ProductionRunError("Persisted forecast contains an invalid numerical value.") from exc
        if not math.isfinite(predicted) or predicted <= 0 or not math.isfinite(delta):
            raise ProductionRunError("Persisted forecast contains a non-positive price or non-finite value.")
        if (lower is not None and not math.isfinite(lower)) or (upper is not None and not math.isfinite(upper)):
            raise ProductionRunError("Persisted forecast bounds contain a non-finite value.")
        if lower is not None and upper is not None and lower > upper:
            raise ProductionRunError("Persisted forecast bounds are inconsistent.")
        if not forecast.model_artifact_id:
            raise ProductionRunError("Persisted production forecast has no model artifact linkage.")
        same_target = db.query(Forecast).filter(
            Forecast.company_id == company.id,
            Forecast.model_id == metadata.id,
            Forecast.target_date == target_date,
            Forecast.is_demo.is_(False),
        ).all()
        if len(same_target) != 1 or same_target[0].pipeline_run_id != run.id:
            raise ProductionRunError("Forecast target has a duplicate or competing run lineage.")
        if approved_artifacts is not None:
            expected_artifact = approved_artifacts.get(key)
            if expected_artifact is None or forecast.model_artifact_id != expected_artifact.id:
                raise ProductionRunError("Persisted forecast is not linked to the approved active model artifact.")
        if bundle_entries is not None:
            entry = bundle_entries.get(key)
            artifact = db.query(ModelArtifact).filter(ModelArtifact.id == forecast.model_artifact_id).one_or_none()
            if entry is None or artifact is None:
                raise ProductionRunError("Persisted forecast artifact is absent from the approved model bundle.")
            expected_values = {
                "company_id": company.id,
                "model_metadata_id": metadata.id,
                "bundle_version": bundle_version,
                "artifact_format": entry["artifact_format"],
                "artifact_path": entry["artifact_relative_path"],
                "artifact_sha256": entry["artifact_sha256"],
                "trained_through": date.fromisoformat(entry["trained_through"]),
                "data_row_count": entry["data_row_count"],
            }
            if any(getattr(artifact, field) != value for field, value in expected_values.items()):
                raise ProductionRunError("Persisted forecast model artifact lineage differs from the approved manifest.")
            if bundle_root is not None:
                metadata = read_verified_artifact_metadata(bundle_root, entry)
                metadata_values = {
                    "source_repository": metadata.get("source_repository"),
                    "source_commit": metadata.get("source_commit"),
                    "historical_data_source_repository": metadata.get("historical_data_source_repository"),
                    "historical_data_source_commit": metadata.get("historical_data_source_commit"),
                }
                if any(getattr(artifact, field) != value for field, value in metadata_values.items()):
                    raise ProductionRunError("Persisted forecast source/model provenance differs from approved metadata.")
                try:
                    artifact_hyperparameters = json.loads(artifact.hyperparameters_json)
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ProductionRunError("Persisted artifact hyperparameter lineage is invalid.") from exc
                if artifact_hyperparameters != metadata.get("hyperparameters"):
                    raise ProductionRunError("Persisted artifact hyperparameters differ from approved metadata.")
    return len(rows)


def _verify_completed_session(
    db: Session,
    session: ProductionSession,
    trade_date: date,
    calendar: ApprovedCalendar,
    source_manifest: Path | None,
    expected_source_manifest_sha: str | None,
    artifacts_root: Path,
) -> None:
    if not calendar.is_session(trade_date) or session.calendar_sha256 != calendar.sha256:
        raise ProductionRunError("Completed session calendar provenance is missing or changed.")
    if not session.source_sha256 or not session.source_manifest_sha256 or not session.market_data_import_id:
        raise ProductionRunError("Completed session lacks source-import lineage.")
    if not expected_source_manifest_sha or expected_source_manifest_sha != session.source_manifest_sha256 or not source_manifest:
        raise ProductionRunError("Completed session does not match the current owner-approved source index.")
    source_payload, source_manifest_sha = verify_source_manifest_record(
        source_manifest, expected_source_manifest_sha, trade_date, session.source_sha256
    )
    if source_manifest_sha != session.source_manifest_sha256:
        raise ProductionRunError("Completed session source manifest hash changed.")
    if source_payload.get("source_url") != session.source_url or source_payload.get("reviewed_by") != session.source_reviewer:
        raise ProductionRunError("Completed session source reviewer or URL lineage changed.")

    imported = db.query(MarketDataImport).filter(MarketDataImport.id == session.market_data_import_id).one_or_none()
    if (imported is None or imported.trade_date != trade_date or imported.sha256 != session.source_sha256
            or imported.status != "COMPLETED" or imported.source_type != "PSE_DQR_FILE"):
        raise ProductionRunError("Completed session source import does not match its approved source manifest.")
    imported_count = imported.records_inserted + imported.records_updated + imported.records_unchanged
    if imported_count <= 0:
        raise ProductionRunError("Completed session source import contains no persisted records.")

    if not session.model_bundle_version or not session.model_manifest_sha256 or not session.pipeline_run_id:
        raise ProductionRunError("Completed session lacks approved model or pipeline audit lineage.")
    bundle = Path(artifacts_root) / session.model_bundle_version
    try:
        manifest, manifest_sha = read_verified_manifest(bundle, expected_version=session.model_bundle_version)
        validate_bundle_coverage(manifest.get("entries", []), set(manifest.get("symbols", [])), MODEL_CODES)
    except Exception as exc:
        raise ProductionRunError("Completed session model bundle is unavailable or failed verification.") from exc
    if manifest_sha != session.model_manifest_sha256:
        raise ProductionRunError("Completed session model manifest hash changed.")
    bundle_entries = {
        (str(entry["symbol"]).upper(), str(entry["model_code"]).upper()): entry
        for entry in manifest["entries"]
    }
    expected_pairs = set(bundle_entries)
    approved_symbols = {symbol for symbol, _ in expected_pairs}
    persisted_price_symbols = {
        symbol.upper() for (symbol,) in db.query(Company.symbol)
        .join(DailyPrice, DailyPrice.company_id == Company.id)
        .filter(DailyPrice.trade_date == trade_date, Company.symbol.in_(approved_symbols))
        .all()
    }
    if persisted_price_symbols != approved_symbols:
        raise ProductionRunError("Completed session source import does not have complete approved-symbol price coverage.")
    target_date = calendar.next_session(trade_date)

    run = db.query(PipelineRun).filter(PipelineRun.id == session.pipeline_run_id).one_or_none()
    if (run is None or run.status != "COMPLETED" or run.is_demo_run or run.completed_at is None
            or run.error_message or run.forecasts_generated != len(expected_pairs)
            or run.records_ingested != imported_count):
        raise ProductionRunError("Completed session does not reference a successful matching production PipelineRun.")
    _validate_persisted_forecasts(
        db, run, expected_pairs, trade_date, target_date,
        bundle_entries=bundle_entries, bundle_version=session.model_bundle_version,
        bundle_root=bundle,
    )


def run_session(
    db: Session,
    trade_date: date,
    calendar: ApprovedCalendar,
    source_file: Path | None,
    source_manifest: Path | None,
    expected_source_manifest_sha: str | None,
    settings,
    artifacts_root: Path,
    bundle_version: str,
    *,
    retry_failed: bool = False,
) -> int:
    if not calendar.coverage_start <= trade_date <= calendar.coverage_end:
        raise ProductionRunError("Requested date is outside the approved calendar coverage.")
    _lock_production_session_date(db, trade_date)
    existing = (
        db.query(ProductionSession)
        .filter(ProductionSession.trade_date == trade_date)
        .with_for_update()
        .one_or_none()
    )
    try:
        _validate_retry_authorization(existing, retry_failed, source_file, source_manifest)
    except ProductionRunError:
        db.rollback()
        raise
    if existing and existing.status == "COMPLETED":
        try:
            _verify_completed_session(
                db, existing, trade_date, calendar, source_manifest,
                expected_source_manifest_sha, artifacts_root,
            )
        finally:
            db.rollback()  # Release the transaction-scoped advisory lock after read-only verification.
        logger.info("Completed session %s passed full source, calendar, model, run, and forecast lineage checks.", trade_date)
        return 0
    if existing and existing.status == "RUNNING":
        db.rollback()  # Release the transaction-scoped advisory lock before reporting the active attempt.
        raise ProductionRunError("A production attempt for this trading session is already running.")
    if not calendar.is_session(trade_date):
        _set_session(db, trade_date, "NON_TRADING", calendar.sha256, message="Reviewed calendar marks this date as non-trading.")
        logger.info("Session status: NON_TRADING for %s.", trade_date)
        return 0

    if source_file is None or source_manifest is None or not source_file.is_file():
        _set_session(db, trade_date, "PENDING_SOURCE", calendar.sha256, message="Approved official source file is not staged.")
        logger.error("Session %s is pending its approved official source file.", trade_date)
        return 2
    if not expected_source_manifest_sha:
        _set_session(db, trade_date, "FAILED", calendar.sha256,
                     message="Owner-approved source manifest pin is missing.")
        logger.error("Production session %s has no pinned source-manifest approval.", trade_date)
        return 1
    source_provenance = {}
    source_sha = None
    source_manifest_sha = None
    try:
        source_provenance, source_sha, source_manifest_sha = verify_source_manifest(
            source_file, source_manifest, expected_source_manifest_sha, trade_date
        )
        validate_production_settings(settings)
        companies, model_manifest_sha, approved_artifacts = validate_approved_models(db, artifacts_root, bundle_version)
        tracked_symbols = {company.symbol.upper() for company in companies}
        ingestion = EODIngestionService()
        parsed, parsed_sha = ingestion.ingest_from_file(source_file, target_date=trade_date, db=None)
        if parsed_sha != source_sha or not parsed or any(item.trade_date != trade_date for item in parsed):
            raise ProductionRunError("Official parser output does not match the approved source date and hash.")
        parsed_symbols = {item.symbol.upper() for item in parsed}
        valid, invalid = DataValidator().validate_dataset(parsed, target_date=trade_date)
        invalid_tracked = {str(item.get("symbol", "")).strip().upper() for item in invalid} & tracked_symbols
        if invalid_tracked or not tracked_symbols.issubset({item.symbol.upper() for item in valid}):
            raise ProductionRunError("Official source failed tracked-symbol validation or coverage.")
        if not tracked_symbols.issubset(parsed_symbols):
            raise ProductionRunError("Official source does not cover every active tracked symbol.")
    except Exception as exc:
        _set_session(
            db, trade_date, "FAILED", calendar.sha256, source_sha=source_sha,
            source_manifest_sha=source_manifest_sha,
            source_url=source_provenance.get("source_url") if source_provenance else None,
            source_reviewer=source_provenance.get("reviewed_by") if source_provenance else None,
            message="Source or production gates failed; see restricted service journal for diagnostics.",
        )
        logger.exception("Source or production gate rejected session %s.", trade_date)
        return 1

    run = PipelineRun(status="RUNNING", started_at=datetime.now(timezone.utc), is_demo_run=False)
    db.add(run)
    db.flush()
    _set_session(
        db, trade_date, "RUNNING", calendar.sha256, source_sha=source_sha,
        source_manifest_sha=source_manifest_sha, source_url=source_provenance.get("source_url"),
        source_reviewer=source_provenance.get("reviewed_by"),
        model_bundle_version=bundle_version,
        model_manifest_sha256=model_manifest_sha,
        pipeline_run_id=run.id, message="Verified source and approved model bundle; inference started.",
        commit=False,
    )
    db.commit()  # Persist the claim while holding the advisory lock before inference begins.
    db.refresh(run)

    import_id = None
    source_import_created = False
    try:
        existing_import = _verify_idempotent_import(db, source_sha, trade_date, tracked_symbols)
        if existing_import is None:
            imported_count, source_sha, import_id = _ingest_verified_source(
                db, source_file, trade_date, tracked_symbols, ingestion
            )
            source_import_created = True
        else:
            imported_count, import_id = existing_import
        _set_session(
            db, trade_date, "RUNNING", calendar.sha256, source_sha=source_sha,
            source_manifest_sha=source_manifest_sha, source_url=source_provenance.get("source_url"),
            source_reviewer=source_provenance.get("reviewed_by"),
            market_data_import_id=import_id, model_bundle_version=bundle_version,
            model_manifest_sha256=model_manifest_sha, pipeline_run_id=run.id,
            message="Approved source import and model bundle verified; inference started.",
            commit=False,
        )
        expected_forecast_date = calendar.next_session(trade_date)
        summary = RealForecastService(db=db, calendar=calendar).generate_and_persist_forecasts(
            artifacts_root=artifacts_root,
            bundle_version=bundle_version,
            target_symbols=sorted(tracked_symbols),
            model_codes=MODEL_CODES,
            dry_run=False,
            pipeline_run=run,
            records_ingested=imported_count,
            expected_origin_date=trade_date,
            as_of_date=trade_date,
            commit_transaction=False,
        )
        expected_pairs = {(symbol, model) for symbol in tracked_symbols for model in MODEL_CODES}
        if summary.status != "PENDING_COMMIT":
            raise ProductionRunError("Real inference did not complete successfully.")
        validate_forecast_outcomes(summary.items, expected_pairs, trade_date, expected_forecast_date)
        if not expected_pairs:
            raise ProductionRunError("Real inference did not produce complete active-symbol/model coverage.")
        persisted_count = _validate_persisted_forecasts(
            db, run, expected_pairs, trade_date, expected_forecast_date,
            approved_artifacts=approved_artifacts,
        )
        if persisted_count != len(expected_pairs):
            raise ProductionRunError("Every required forecast was not persisted by this production run.")
        finalization_claim = _lock_finalization_claim(db, trade_date, run.id)
        if finalization_claim.status == "COMPLETED":
            _verify_completed_session(
                db, finalization_claim, trade_date, calendar, source_manifest,
                expected_source_manifest_sha, artifacts_root,
            )
            db.rollback()
            logger.info("Production session %s was already finalized by a competing execution.", trade_date)
            return 0
        run.status = "COMPLETED"
        run.completed_at = datetime.now(timezone.utc)
        run.records_ingested = imported_count
        run.forecasts_generated = persisted_count
        run.error_message = None
        _set_session(
            db, trade_date, "COMPLETED", calendar.sha256, source_sha=source_sha,
            source_manifest_sha=source_manifest_sha, source_url=source_provenance.get("source_url"),
            source_reviewer=source_provenance.get("reviewed_by"),
            market_data_import_id=import_id, model_bundle_version=bundle_version,
            model_manifest_sha256=model_manifest_sha,
            pipeline_run_id=run.id,
            message=(f"Completed with {len(summary.items)} verified forecast outcomes; "
                     f"source manifest {source_manifest_sha}; model manifest {model_manifest_sha}; "
                     f"reviewer {source_provenance['reviewed_by']}.") ,
            commit=False,
        )
        db.flush()
        db.commit()
        logger.info(
            "Production session %s completed: %d outcomes, %d persisted, %d unchanged.",
            trade_date, len(summary.items), summary.total_forecasts_persisted, summary.total_forecasts_unchanged,
        )
        return 0
    except Exception as exc:
        db.rollback()
        durable_session = (db.query(ProductionSession)
                           .filter(ProductionSession.trade_date == trade_date)
                           .one_or_none())
        if (durable_session is not None and durable_session.status == "COMPLETED"
                and durable_session.pipeline_run_id == run.id):
            try:
                _verify_completed_session(
                    db, durable_session, trade_date, calendar, source_manifest,
                    expected_source_manifest_sha, artifacts_root,
                )
            except Exception:
                db.rollback()
                logger.exception("Competing finalization left an invalid completed session for %s.", trade_date)
                return 1
            db.rollback()
            logger.info("Production session %s was completed by a competing execution.", trade_date)
            return 0
        if (durable_session is None or durable_session.status != "RUNNING"
                or durable_session.pipeline_run_id != run.id):
            db.rollback()
            logger.error("Production session %s claim changed; preserving the current durable state.", trade_date)
            return 1
        if source_import_created:
            import_id = None
        failed = db.query(PipelineRun).filter(PipelineRun.id == run.id).one_or_none()
        if failed is not None:
            failed.status = "FAILED"
            failed.completed_at = datetime.now(timezone.utc)
            failed.error_message = str(exc)
        _set_session(
            db, trade_date, "FAILED", calendar.sha256, source_sha=source_sha,
            source_manifest_sha=source_manifest_sha, source_url=source_provenance.get("source_url"),
            source_reviewer=source_provenance.get("reviewed_by"),
            market_data_import_id=import_id, model_bundle_version=bundle_version,
            model_manifest_sha256=model_manifest_sha,
            pipeline_run_id=run.id, message="Production session failed; see restricted service journal for details.",
            commit=False,
        )
        # Failure audit and session status move together after unverified writes roll back.
        db.commit()
        logger.exception("Production EOD session failed for %s.", trade_date)
        return 1


def _manila_date() -> date:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Manila")).date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheduled", action="store_true", help="Use today's date in Asia/Manila.")
    parser.add_argument("--trade-date", type=date.fromisoformat, help="Exact session date in YYYY-MM-DD format.")
    parser.add_argument("--source-file", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--calendar-manifest", type=Path, default=os.getenv("PSE_CALENDAR_MANIFEST"))
    parser.add_argument("--source-dir", type=Path, default=Path(os.getenv("PSE_INCOMING_DIR", "/var/lib/pse-pulse/incoming")))
    parser.add_argument("--reconcile-pending", action="store_true")
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="Explicitly retry the exact failed session selected by --trade-date.",
    )
    parser.add_argument("--bundle-version", default=os.getenv("MODEL_ARTIFACT_BUNDLE_VERSION"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.scheduled == bool(args.trade_date):
        raise SystemExit("Choose exactly one of --scheduled or --trade-date.")
    if args.retry_failed and (args.scheduled or args.reconcile_pending):
        raise SystemExit("--retry-failed requires one exact --trade-date and cannot reconcile pending sessions.")
    settings = get_settings()
    calendar_path = args.calendar_manifest
    calendar_sha = os.getenv("PSE_CALENDAR_MANIFEST_SHA256", "")
    source_index_path = Path(os.getenv("PSE_SOURCE_APPROVAL_INDEX", "/etc/pse-pulse/source-approval-index.json"))
    source_index_sha = os.getenv("PSE_SOURCE_APPROVAL_INDEX_SHA256", "")
    if not calendar_path:
        logger.error("Approved calendar path is not configured.")
        return 1
    db = SessionLocal()
    try:
        if args.reconcile_pending:
            pending = db.query(ProductionSession).filter(
                ProductionSession.status == "PENDING_SOURCE",
                ProductionSession.trade_date <= (_manila_date() if args.scheduled else args.trade_date),
            ).order_by(ProductionSession.trade_date.asc()).all()
            for item in pending:
                path = _find_source(args.source_dir, item.trade_date)
                if path is None:
                    logger.error("Pending source still unavailable for %s.", item.trade_date)
                    return 2
                manifest_path, manifest_sha = verify_source_approval_index(
                    source_index_path, source_index_sha, item.trade_date, args.source_dir
                )
                approved_calendar = verify_calendar_manifest(calendar_path, calendar_sha, item.trade_date)
                code = run_session(
                    db, item.trade_date, approved_calendar, path, manifest_path,
                    manifest_sha, settings,
                    Path(settings.MODEL_ARTIFACTS_DIR), args.bundle_version or "",
                )
                if code:
                    return code
        target_date = _manila_date() if args.scheduled else args.trade_date
        assert target_date is not None
        source = args.source_file or _find_source(args.source_dir, target_date)
        existing = db.query(ProductionSession).filter(ProductionSession.trade_date == target_date).one_or_none()
        if source is None:
            if existing and existing.status == "COMPLETED":
                manifest, manifest_sha = verify_source_approval_index(
                    source_index_path, source_index_sha, target_date, args.source_dir
                )
            else:
                manifest = None
                manifest_sha = None
        else:
            manifest, manifest_sha = verify_source_approval_index(
                source_index_path, source_index_sha, target_date, args.source_dir
            )
            if args.source_manifest is not None and args.source_manifest.resolve() != manifest.resolve():
                raise ProductionRunError("Explicit source manifest differs from the owner-pinned approval index.")
        approved_calendar = verify_calendar_manifest(calendar_path, calendar_sha, target_date)
        return run_session(
            db, target_date, approved_calendar, source, manifest,
            manifest_sha, settings,
            Path(settings.MODEL_ARTIFACTS_DIR), args.bundle_version or "",
            retry_failed=args.retry_failed,
        )
    except Exception:
        logger.exception("Production EOD preflight failed; no synthetic fallback was attempted.")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
