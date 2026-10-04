"""Sequential offline refit orchestration for the authoritative 45-artifact bundle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import importlib.metadata
import json
import logging
import math
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.domain.company_universe import get_all_configured_symbols
from backend.app.forecasting.real.artifacts.authoritative import (
    AUTHORITATIVE_REGIME,
    load_authoritative_model,
    persist_authoritative_arima,
    persist_authoritative_lir,
)
from backend.app.forecasting.real.artifacts.bundle import (
    ACCEPTANCE_BUNDLE_VERSION,
    BUNDLE_SCHEMA_ID,
    BUNDLE_SCHEMA_VERSION,
    EXPECTED_HISTORY_FIRST_DATE,
    EXPECTED_ROWS_PER_SYMBOL,
    EXPECTED_TRAINED_THROUGH,
    MODEL_FAMILY_ORDER,
    ProductionBundleError,
    build_atomically,
    sha256_file,
    verify_bundle,
)
from backend.app.forecasting.real.calendar import PSETradingCalendar, manila_now
from backend.app.forecasting.real.config import DEFAULT_ARIMA_CONFIG, DEFAULT_LAG_REGRESSION_CONFIG
from backend.app.forecasting.real.domain import OhlcvRecord
from backend.app.forecasting.real.features.regression_features import (
    build_regression_dataset,
)
from backend.app.forecasting.real.history import load_company_ohlcv_history
from backend.app.forecasting.real.inference.predictor import predict_with_production_model
from backend.app.forecasting.real.models.arima import ConvergenceStatus
from backend.app.forecasting.real.selections import (
    OFFICIAL_REPOSITORY,
    SELECTION_SOURCE_COMMIT,
    SELECTION_SOURCE_FILE,
    SELECTION_SOURCE_GIT_BLOB,
    SELECTION_SOURCE_SHA256,
    AuthoritativeModelSelection,
    load_selection_catalog,
)
from backend.app.models.company import Company
from backend.app.models.forecast import Forecast
from backend.app.models.model_artifact import ModelArtifact
from backend.app.models.price import DailyPrice
from backend.pipeline.bootstrap.official_repo_csv import OfficialRepoHistoricalProvider
from backend.pipeline.bootstrap.provenance import OfficialSourceVerifier
from backend.app.forecasting.real.training.refit_arima import refit_arima_for_production
from backend.app.forecasting.real.training.refit_lir import refit_lir_for_production

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BundlePreflight:
    symbols: tuple[str, ...]
    records_by_symbol: dict[str, tuple[OhlcvRecord, ...]]
    source_csv_sha256: dict[str, str]
    canonical_history_rows: int
    post_cutoff_rows: int


def _finite_positive_record(record: OhlcvRecord, symbol: str) -> None:
    values = (record.open, record.high, record.low, record.close, record.volume)
    if any(not math.isfinite(value) for value in values):
        raise ProductionBundleError(f"{symbol} {record.trading_date}: non-finite OHLCV")
    if min(record.open, record.high, record.low, record.close) <= 0 or record.volume < 0:
        raise ProductionBundleError(f"{symbol} {record.trading_date}: invalid OHLCV range")
    if record.high < max(record.open, record.low, record.close) or record.low > min(record.open, record.high, record.close):
        raise ProductionBundleError(f"{symbol} {record.trading_date}: inconsistent OHLC bounds")


def preflight_history(
    *,
    db: Session,
    official_source_root: Path,
) -> BundlePreflight:
    """Verify exact canonical DB coverage and row-level parity before training."""
    catalog = load_selection_catalog()
    symbols = tuple(get_all_configured_symbols())
    if len(symbols) != 15 or len(set(symbols)) != 15 or set(catalog) != set(symbols):
        raise ProductionBundleError("Canonical universe and authoritative catalog do not match 15/15")
    companies = db.query(Company).filter(Company.symbol.in_(symbols)).all()
    company_by_symbol = {company.symbol: company for company in companies}
    if set(company_by_symbol) != set(symbols):
        raise ProductionBundleError(f"Database companies missing: {sorted(set(symbols) - set(company_by_symbol))}")

    verified_source = OfficialSourceVerifier().verify(source_root=official_source_root)
    if verified_source.commit != SELECTION_SOURCE_COMMIT:
        raise ProductionBundleError("Historical source commit differs from the accepted pin")
    csv_provider = OfficialRepoHistoricalProvider()
    records_by_symbol: dict[str, tuple[OhlcvRecord, ...]] = {}
    source_shas: dict[str, str] = {}
    duplicate_count = 0
    total_rows = 0
    post_cutoff_rows = 0
    for symbol in symbols:
        company = company_by_symbol[symbol]
        db_rows = (
            db.query(DailyPrice)
            .filter(
                DailyPrice.company_id == company.id,
                DailyPrice.trade_date <= EXPECTED_TRAINED_THROUGH,
            )
            .order_by(DailyPrice.trade_date.asc())
            .all()
        )
        records = load_company_ohlcv_history(
            db, company.id, end_date=EXPECTED_TRAINED_THROUGH
        )
        if len(records) != EXPECTED_ROWS_PER_SYMBOL:
            raise ProductionBundleError(f"{symbol}: expected 1,649 history rows, found {len(records)}")
        if records[0].trading_date != EXPECTED_HISTORY_FIRST_DATE or records[-1].trading_date != EXPECTED_TRAINED_THROUGH:
            raise ProductionBundleError(f"{symbol}: accepted training date boundary mismatch")
        dates = tuple(record.trading_date for record in records)
        if dates != tuple(sorted(dates)) or len(set(dates)) != len(dates):
            raise ProductionBundleError(f"{symbol}: history is unordered or contains duplicate dates")
        for record in records:
            _finite_positive_record(record, symbol)
        duplicate_count += len(db_rows) - len({row.trade_date for row in db_rows})
        if duplicate_count:
            raise ProductionBundleError("Database has duplicate canonical symbol/date records")
        official_rows, official_sha = csv_provider.parse_file(
            verified_source.raw_data_dir / f"{symbol}.csv", symbol
        )
        if len(official_rows) != EXPECTED_ROWS_PER_SYMBOL:
            raise ProductionBundleError(f"{symbol}: official source does not contain exactly 1,649 rows")
        for official, db_record in zip(official_rows, records, strict=True):
            expected = (official.open_price, official.high_price, official.low_price, official.close_price, official.volume)
            actual = tuple(Decimal(str(value)) for value in (db_record.open, db_record.high, db_record.low, db_record.close, db_record.volume))
            if official.trade_date != db_record.trading_date or any(abs(left - right) > Decimal("0.00005") for left, right in zip(expected, actual, strict=True)):
                raise ProductionBundleError(f"{symbol} {official.trade_date}: OHLCV differs from pinned official CSV")
        source_shas[symbol] = official_sha
        records_by_symbol[symbol] = records
        total_rows += len(records)
        post_cutoff_rows += db.query(func.count(DailyPrice.id)).filter(
            DailyPrice.company_id == company.id,
            DailyPrice.trade_date > EXPECTED_TRAINED_THROUGH,
        ).scalar()
    if total_rows != 24_735:
        raise ProductionBundleError(f"Expected 24,735 canonical history rows, found {total_rows}")
    LOGGER.info(
        "Preflight passed companies=%d rows=%d parity_mismatches=0 post_cutoff_rows=%d",
        len(symbols), total_rows, post_cutoff_rows,
    )
    return BundlePreflight(symbols, records_by_symbol, source_shas, total_rows, post_cutoff_rows)


def _build_environment() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "numpy": importlib.metadata.version("numpy"),
        "scikit_learn": importlib.metadata.version("scikit-learn"),
        "statsmodels": importlib.metadata.version("statsmodels"),
        "pytorch": importlib.metadata.version("torch"),
    }


def _manifest_entry(
    *,
    symbol: str,
    model_code: str,
    bundle_directory: Path,
    artifact_path: Path,
    metadata_path: Path,
    selection: AuthoritativeModelSelection,
    model_evidence: dict[str, Any],
) -> dict[str, Any]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    relative_artifact = artifact_path.relative_to(bundle_directory).as_posix()
    relative_metadata = metadata_path.relative_to(bundle_directory).as_posix()
    selection_summary = {
        "LAG_REGRESSION": {"alpha": selection.lir_alpha},
        "ARIMA": selection.arima.as_dict(),
        "LSTM": selection.lstm.as_dict(),
    }[model_code]
    return {
        "symbol": symbol,
        "model_code": model_code,
        "model_version": metadata["model_version"],
        "artifact_format": metadata["artifact_format"],
        "artifact_relative_path": relative_artifact,
        "artifact_sha256": sha256_file(artifact_path),
        "artifact_size_bytes": artifact_path.stat().st_size,
        "metadata_relative_path": relative_metadata,
        "metadata_sha256": sha256_file(metadata_path),
        "trained_through": metadata["trained_through"],
        "data_row_count": metadata["data_row_count"],
        "selection": selection_summary,
        "selection_provenance": selection.provenance.as_dict(),
        "model_evidence": model_evidence,
    }


def _persist_lstm_manifest_entry(
    *,
    persist_artifact: Callable[..., tuple[Path, Path, dict[str, Any]]],
    output_directory: Path,
    bundle_directory: Path,
    symbol: str,
    model_version: str,
    selection: AuthoritativeModelSelection,
    production_fit: Any,
) -> dict[str, Any]:
    """Persist LSTM via its accepted three-value API, then bind actual files."""
    artifact_path, metadata_path, metadata = persist_artifact(
        output_directory=output_directory,
        symbol=symbol,
        model_version=model_version,
        fitted=production_fit.fitted,
        data_row_count=EXPECTED_ROWS_PER_SYMBOL,
        trained_through=EXPECTED_TRAINED_THROUGH,
        formal_selected_epoch_count=selection.formal_lstm_selected_epoch_count,
        selection_provenance=selection.provenance,
    )
    if metadata.get("artifact_sha256") != sha256_file(artifact_path):
        raise ProductionBundleError(f"{symbol}/LSTM: persisted artifact checksum differs from metadata")
    return _manifest_entry(
        symbol=symbol,
        model_code="LSTM",
        bundle_directory=bundle_directory,
        artifact_path=artifact_path,
        metadata_path=metadata_path,
        selection=selection,
        model_evidence={
            **selection.lstm.as_dict(),
            "formal_selected_epoch_count": selection.formal_lstm_selected_epoch_count,
            "production_selected_epoch_count": production_fit.epoch_selection.selected_epoch_count,
            "seed": production_fit.fitted.seed,
        },
    )


def _acceptance_inference(bundle_directory: Path, preflight: BundlePreflight) -> list[dict[str, Any]]:
    from backend.app.forecasting.real.artifacts.lstm_state import load_lstm_state_artifact
    from backend.app.forecasting.real.selections import load_selection_catalog

    catalog = load_selection_catalog()
    calendar = PSETradingCalendar()
    acceptance: list[dict[str, Any]] = []
    for symbol in preflight.symbols:
        records = preflight.records_by_symbol[symbol]
        target_date = calendar.next_trading_day(records[-1].trading_date)
        if target_date != date(2026, 10, 2):
            raise ProductionBundleError(f"{symbol}: calendar returned unexpected next target {target_date}")
        origin_close = records[-1].close
        for family in MODEL_FAMILY_ORDER:
            if family == "LSTM":
                loaded = load_lstm_state_artifact(
                    symbol_directory=bundle_directory / symbol,
                    expected_symbol=symbol,
                    expected_model_version=ACCEPTANCE_BUNDLE_VERSION,
                    expected_trained_through=EXPECTED_TRAINED_THROUGH,
                    expected_data_row_count=EXPECTED_ROWS_PER_SYMBOL,
                )
                lookback = catalog[symbol].lstm.lookback
                latest_deltas = tuple(
                    records[index].close - records[index - 1].close
                    for index in range(len(records) - lookback, len(records))
                )
                prediction = float(loaded.model.predict_delta_sequences([latest_deltas])[0])
                formal_epochs = loaded.metadata["hyperparameters"]["formal_selected_epoch_count"]
                production_epochs = loaded.metadata["hyperparameters"]["production_selected_epoch_count"]
            else:
                model, metadata = load_authoritative_model(
                    symbol_directory=bundle_directory / symbol,
                    expected_symbol=symbol,
                    expected_model_code=family,
                    expected_model_version=ACCEPTANCE_BUNDLE_VERSION,
                    trained_through=EXPECTED_TRAINED_THROUGH,
                    data_row_count=EXPECTED_ROWS_PER_SYMBOL,
                )
                forecast = predict_with_production_model(
                    fitted_model=model, metadata=metadata, records=records
                )
                prediction = float(forecast.predicted_delta)
                formal_epochs = None
                production_epochs = None
            predicted_close = origin_close + prediction
            if not math.isfinite(prediction) or not math.isfinite(predicted_close) or predicted_close <= 0:
                raise ProductionBundleError(f"{symbol}/{family}: invalid one-step inference output")
            row = {
                "symbol": symbol,
                "model_code": family,
                "origin_date": records[-1].trading_date.isoformat(),
                "target_date": target_date.isoformat(),
                "origin_close": origin_close,
                "predicted_delta": prediction,
                "predicted_close": predicted_close,
                "safe_reload_passed": True,
            }
            if family == "LSTM":
                row["formal_selected_epoch_count"] = formal_epochs
                row["production_selected_epoch_count"] = production_epochs
            acceptance.append(row)
            LOGGER.info("Accepted safe reload and one-step inference symbol=%s model=%s", symbol, family)
    if len(acceptance) != 45:
        raise ProductionBundleError(f"Expected 45 inference results, found {len(acceptance)}")
    return acceptance


def _database_row_counts(db: Session) -> tuple[int, int]:
    return (
        db.query(func.count(Forecast.id)).scalar(),
        db.query(func.count(ModelArtifact.id)).scalar(),
    )


def _require_unchanged_database_rows(
    db: Session,
    *,
    starting_counts: tuple[int, int],
) -> tuple[int, int]:
    current_counts = _database_row_counts(db)
    if current_counts != starting_counts:
        raise ProductionBundleError(
            "Acceptance build changed forecast or ModelArtifact database rows "
            f"(started={starting_counts}, current={current_counts})"
        )
    return current_counts


def _promote_validation_evidence(
    staging_validation: Path,
    validation_path: Path,
    *,
    on_promoted: Callable[[], None],
) -> None:
    """Publish evidence without overwriting an existing path."""
    try:
        os.link(staging_validation, validation_path)
    except FileExistsError as exc:
        raise ProductionBundleError("bundle_validation.json appeared during finalization") from exc
    on_promoted()
    staging_validation.unlink()


def _finalize_bundle_with_validation(
    *,
    repository_root: Path,
    output_root: Path,
    bundle_version: str,
    builder: Callable[[Path], Any],
    verifier: Callable[[Path], Any],
    staging_validation: Path,
    validation_path: Path,
    starting_counts: tuple[int, int],
    read_counts: Callable[[], tuple[int, int]],
) -> tuple[Path, Any, tuple[int, int]]:
    """Finalize bundle and sidecar as one fail-closed operation."""
    final_directory: Path | None = None
    published_by_this_invocation = False
    validation_created_by_this_invocation = False
    try:
        final_directory, verification = build_atomically(
            repository_root=repository_root,
            output_root=output_root,
            bundle_version=bundle_version,
            builder=builder,
            verifier=verifier,
        )
        # build_atomically only returns after this invocation's no-clobber rename.
        published_by_this_invocation = True

        def mark_validation_created() -> None:
            nonlocal validation_created_by_this_invocation
            validation_created_by_this_invocation = True

        _promote_validation_evidence(
            staging_validation,
            validation_path,
            on_promoted=mark_validation_created,
        )
        final_counts = read_counts()
        if final_counts != starting_counts:
            raise ProductionBundleError(
                "Acceptance build changed forecast or ModelArtifact database rows "
                f"(started={starting_counts}, current={final_counts})"
            )
        return final_directory, verification, final_counts
    except Exception:
        staging_validation.unlink(missing_ok=True)
        if validation_created_by_this_invocation:
            validation_path.unlink(missing_ok=True)
        if published_by_this_invocation and final_directory is not None:
            shutil.rmtree(final_directory, ignore_errors=True)
        raise


def build_authoritative_bundle(
    *,
    db: Session,
    repository_root: Path,
    output_root: Path,
    official_source_root: Path,
    bundle_version: str = ACCEPTANCE_BUNDLE_VERSION,
) -> dict[str, Any]:
    """Preflight, sequentially train, verify, infer, and atomically finalize all 45 models."""
    if bundle_version != ACCEPTANCE_BUNDLE_VERSION:
        raise ProductionBundleError("The Phase 3B.2 acceptance bundle version is fixed")
    preflight = preflight_history(db=db, official_source_root=official_source_root)
    selections = load_selection_catalog()
    starting_counts = _database_row_counts(db)
    starting_forecasts, starting_artifacts = starting_counts
    acceptance_results: list[dict[str, Any]] = []
    resolved_output_root = Path(output_root).expanduser().resolve()
    staging_validation = resolved_output_root / ".bundle_validation.phase3b2.tmp"
    validation_path = resolved_output_root / "bundle_validation.json"
    if os.path.lexists(staging_validation):
        raise ProductionBundleError("Temporary bundle validation evidence already exists; refusing overwrite")
    if os.path.lexists(validation_path):
        raise ProductionBundleError("bundle_validation.json already exists; refusing overwrite")

    def builder(staging: Path) -> None:
        from backend.app.forecasting.real.training.lstm import refit_lstm_for_production

        entries: list[dict[str, Any]] = []
        for symbol in preflight.symbols:
            records = preflight.records_by_symbol[symbol]
            selection = selections[symbol]
            symbol_dir = staging / symbol
            symbol_dir.mkdir()
            LOGGER.info("Building authoritative artifacts for %s", symbol)

            from backend.app.forecasting.real.artifacts.lstm_state import persist_lstm_state_artifact

            lir_dataset = build_regression_dataset(records, DEFAULT_LAG_REGRESSION_CONFIG.features)
            fitted_lir = refit_lir_for_production(lir_dataset, chosen_alpha=selection.lir_alpha)
            if not fitted_lir.fit_metadata.converged:
                raise ProductionBundleError(f"{symbol}/LAG_REGRESSION: LASSO did not converge")
            _, lir_artifact, lir_metadata = persist_authoritative_lir(
                output_directory=symbol_dir,
                symbol=symbol,
                model_version=bundle_version,
                fitted=fitted_lir,
                trained_through=EXPECTED_TRAINED_THROUGH,
                data_row_count=EXPECTED_ROWS_PER_SYMBOL,
                formal_selected_features_evidence=selection.lir_selected_features_evidence,
                selection_provenance=selection.provenance,
            )
            entries.append(_manifest_entry(
                symbol=symbol, model_code="LAG_REGRESSION", bundle_directory=staging,
                artifact_path=lir_artifact, metadata_path=lir_metadata, selection=selection,
                model_evidence={
                    "authoritative_alpha": selection.lir_alpha,
                    "production_pacf_selected_return_lags": list(fitted_lir.pacf_selected_lags),
                    "production_feature_names": list(fitted_lir.fit_metadata.feature_names),
                    "production_feature_count": len(fitted_lir.fit_metadata.feature_names),
                    "formal_selected_features_evidence_only": list(selection.lir_selected_features_evidence),
                },
            ))

            arima_fit = refit_arima_for_production(
                records, selected_specification=selection.arima, config=DEFAULT_ARIMA_CONFIG
            )
            if arima_fit.model.convergence is not ConvergenceStatus.CONFIRMED_CONVERGED:
                raise ProductionBundleError(f"{symbol}/ARIMA: convergence was not confirmed")
            _, arima_artifact, arima_metadata = persist_authoritative_arima(
                output_directory=symbol_dir,
                symbol=symbol,
                model_version=bundle_version,
                fitted=arima_fit.model,
                trained_through=EXPECTED_TRAINED_THROUGH,
                data_row_count=EXPECTED_ROWS_PER_SYMBOL,
                selection_provenance=selection.provenance,
            )
            entries.append(_manifest_entry(
                symbol=symbol, model_code="ARIMA", bundle_directory=staging,
                artifact_path=arima_artifact, metadata_path=arima_metadata, selection=selection,
                model_evidence={
                    "authoritative_order": list(selection.arima.order),
                    "authoritative_trend": selection.arima.trend,
                    "convergence_status": arima_fit.model.convergence.value,
                    "fit_attempts": [attempt.as_dict() for attempt in arima_fit.model.attempts],
                },
            ))

            production_fit = refit_lstm_for_production(records, selected_specification=selection.lstm)
            entries.append(_persist_lstm_manifest_entry(
                persist_artifact=persist_lstm_state_artifact,
                output_directory=symbol_dir,
                bundle_directory=staging,
                symbol=symbol,
                model_version=bundle_version,
                selection=selection,
                production_fit=production_fit,
            ))
        entries.sort(key=lambda entry: (entry["symbol"], MODEL_FAMILY_ORDER.index(entry["model_code"])))
        manifest = {
            "schema_id": BUNDLE_SCHEMA_ID,
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "bundle_version": bundle_version,
            "created_at": manila_now().isoformat(),
            "trained_through": EXPECTED_TRAINED_THROUGH.isoformat(),
            "history_first_date": EXPECTED_HISTORY_FIRST_DATE.isoformat(),
            "history_row_count_per_symbol": EXPECTED_ROWS_PER_SYMBOL,
            "total_history_rows": preflight.canonical_history_rows,
            "post_cutoff_rows_excluded": preflight.post_cutoff_rows,
            "model_artifact_count": 45,
            "metadata_file_count": 45,
            "symbols": list(preflight.symbols),
            "model_families": list(MODEL_FAMILY_ORDER),
            "official_methodology_provenance": {
                "repository": OFFICIAL_REPOSITORY,
                "commit": SELECTION_SOURCE_COMMIT,
            },
            "historical_data_provenance": {
                "repository": OFFICIAL_REPOSITORY,
                "commit": SELECTION_SOURCE_COMMIT,
                "csv_sha256_by_symbol": preflight.source_csv_sha256,
            },
            "authoritative_selection_provenance": {
                **selections[preflight.symbols[0]].provenance.as_dict(),
                "selection_csv_sha256": SELECTION_SOURCE_SHA256,
                "selection_csv_git_blob": SELECTION_SOURCE_GIT_BLOB,
                "selection_source_file": SELECTION_SOURCE_FILE,
            },
            "formal_run": {
                "run_id": selections[preflight.symbols[0]].provenance.formal_run_id,
                "cutoff": selections[preflight.symbols[0]].provenance.formal_cutoff,
                "experiment_git_sha": selections[preflight.symbols[0]].provenance.formal_git_sha,
            },
            "build_environment": _build_environment(),
            "entries": entries,
        }
        acceptance_results.extend(_acceptance_inference(staging, preflight))
        if len(acceptance_results) != 45:
            raise ProductionBundleError("All 45 safe-reload one-step predictions are required")
        staging_validation.write_text(
            json.dumps({"results": acceptance_results}, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        # The manifest is the final file written inside the bundle.
        verify_bundle(staging)
        # Check database row counts before build_atomically is allowed to rename staging.
        _require_unchanged_database_rows(db, starting_counts=starting_counts)

    try:
        final_directory, verification, ending_counts = _finalize_bundle_with_validation(
            repository_root=repository_root,
            output_root=output_root,
            bundle_version=bundle_version,
            builder=builder,
            verifier=verify_bundle,
            staging_validation=staging_validation,
            validation_path=validation_path,
            starting_counts=starting_counts,
            read_counts=lambda: _database_row_counts(db),
        )
    except Exception:
        staging_validation.unlink(missing_ok=True)
        raise
    ending_forecasts, ending_artifacts = ending_counts
    return {
        "bundle_directory": final_directory,
        "validation_path": validation_path,
        "manifest_sha256": sha256_file(final_directory / "manifest.json"),
        "manifest_size_bytes": (final_directory / "manifest.json").stat().st_size,
        "bundle_file_count": sum(1 for path in final_directory.rglob("*") if path.is_file()),
        "artifact_count": 45,
        "metadata_count": 45,
        "safe_reload_count": verification["safe_reload_count"],
        "inference_results": acceptance_results,
        "forecast_rows_delta": ending_forecasts - starting_forecasts,
        "model_artifact_rows_delta": ending_artifacts - starting_artifacts,
        "preflight": {
            "company_count": len(preflight.symbols),
            "canonical_history_rows": preflight.canonical_history_rows,
            "post_cutoff_rows_excluded": preflight.post_cutoff_rows,
            "official_parity_mismatches": 0,
        },
    }
