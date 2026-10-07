"""Production Real Forecast Service.

Coordinates loading verified production model artifacts, computing causal
next-day predictions for PSE tracked equities, enforcing database lineage,
and committing all forecasts atomically within a single transaction.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import uuid

from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.forecasting.real.artifacts.runtime import load_runtime_artifact, read_verified_manifest
from backend.app.forecasting.real.artifacts.schema import (
    ModelArtifactCompatibilityError,
    ProductionModelMetadata,
)
from backend.app.forecasting.real.calendar import PSETradingCalendar
from backend.app.forecasting.real.config import ModelId
from backend.app.forecasting.real.domain import (
    CompanyNextDayForecast,
    ModelForecast,
    OhlcvRecord,
)
from backend.app.forecasting.real.history import load_company_ohlcv_history
from backend.app.forecasting.real.inference.next_day import predict_next_day_with_artifacts
from backend.app.models.company import Company
from backend.app.models.forecast import Forecast
from backend.app.models.model_artifact import ModelArtifact
from backend.app.models.model_metadata import ModelMetadata
from backend.app.models.pipeline_run import PipelineRun

logger = logging.getLogger("pse_pulse_real_forecasting")


class RealForecastingError(Exception):
    """Raised when real forecast generation or persistence fails."""


class RealModelsDisabledError(RealForecastingError):
    """Raised when real models are invoked while REAL_MODELS_ENABLED is false in production."""


class RealForecastIntegrityError(RealForecastingError):
    """Raised when a forecast rerun discovers differing values or tampering, violating immutability."""


@dataclass
class ForecastItemSummary:
    """Summary of a single generated forecast."""
    symbol: str
    model_code: str
    origin_date: date
    target_date: date
    predicted_close: float
    predicted_delta: float
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    artifact_id: str
    status: str = "PERSISTED"


@dataclass
class RealForecastExecutionSummary:
    """Detailed summary of a batch real forecasting execution."""
    run_id: str
    status: str
    pipeline_run_id: Optional[int]
    total_companies: int
    total_forecasts_generated: int
    total_forecasts_persisted: int
    total_forecasts_unchanged: int = 0
    symbols_processed: List[str] = field(default_factory=list)
    items: List[ForecastItemSummary] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _normalize_model_code(model: str | ModelId) -> str:
    """Normalize model identifier to canonical DB code."""
    val = model.value if isinstance(model, ModelId) else str(model)
    val_upper = val.upper()
    if val_upper in ("LAG_REG", "LAG_REGRESSION"):
        return "LAG_REGRESSION"
    if val_upper == "ARIMA":
        return "ARIMA"
    if val_upper == "LSTM":
        return "LSTM"
    return val_upper


class RealForecastService:

    """Coordinates verified artifact loading, inference, lineage, and atomic persistence."""

    def __init__(self, db: Session, calendar: Optional[PSETradingCalendar] = None):
        self.db = db
        self.calendar = calendar or PSETradingCalendar()
        self.settings = get_settings()

    def generate_and_persist_forecasts(
        self,
        artifacts_root: Path | str,
        bundle_version: str,
        target_symbols: Optional[Sequence[str]] = None,
        model_codes: Sequence[str] = (ModelId.LAG_REGRESSION.value, ModelId.ARIMA.value, ModelId.LSTM.value),
        dry_run: bool = False,
    ) -> RealForecastExecutionSummary:
        """Run real next-session inference across companies and persist atomically.

        Args:
            artifacts_root: Directory containing model artifact bundles.
            bundle_version: Target bundle version (e.g. '2026.03.01-v1').
            target_symbols: Optional subset of symbols (defaults to all active companies).
            model_codes: List of model codes to infer (e.g. ['LAG_REGRESSION', 'ARIMA']).
            dry_run: If True, execute inference and validation without database writes.

        Returns:
            RealForecastExecutionSummary with complete details.

        Raises:
            RealModelsDisabledError: If REAL_MODELS_ENABLED is false.
            RealForecastIntegrityError: If existing forecast values differ on rerun.
            RealForecastingError: If any symbol/model fails inference or persistence.
        """
        # 1. Production safety gate check
        current_settings = get_settings()
        if not current_settings.REAL_MODELS_ENABLED:
            raise RealModelsDisabledError(
                f"REAL_MODELS_ENABLED is False in {current_settings.ENVIRONMENT} environment. "
                "Real model execution is disabled by configuration."
            )

        artifacts_path = Path(artifacts_root).resolve()
        bundle_dir = artifacts_path / bundle_version
        if not bundle_dir.exists():
            raise RealForecastingError(
                f"Model bundle directory not found: {bundle_dir}"
            )
        manifest, manifest_sha = read_verified_manifest(bundle_dir, expected_version=bundle_version)
        entries_by_key = {(item["symbol"], item["model_code"]): item for item in manifest["entries"]}

        run_uuid = f"real-infer-{uuid.uuid4().hex[:12]}"
        now_utc = datetime.now(timezone.utc)

        # 2. Query target companies
        query = self.db.query(Company).filter(Company.is_active == True)
        if target_symbols:
            query = query.filter(Company.symbol.in_(target_symbols))
        companies = query.order_by(Company.symbol.asc()).all()

        if not companies:
            raise RealForecastingError("No active companies found matching criteria.")

        # 3. Resolve ModelMetadata records
        model_meta_map: Dict[str, ModelMetadata] = {}
        for m_code in model_codes:
            norm_code = _normalize_model_code(m_code)
            matching_metadata = self.db.query(ModelMetadata).filter(ModelMetadata.code == norm_code).all()
            if len(matching_metadata) != 1:
                raise RealForecastingError(
                    f"Expected exactly one ModelMetadata record for code '{norm_code}', found {len(matching_metadata)}."
                )
            model_meta_map[norm_code] = matching_metadata[0]

        # 4. Initialize PipelineRun audit record if not dry-run
        pipeline_run: Optional[PipelineRun] = None
        if not dry_run:
            pipeline_run = PipelineRun(
                run_id=run_uuid,
                status="RUNNING",
                started_at=now_utc,
                records_ingested=0,
                forecasts_generated=0,
                is_demo_run=False,
            )
            self.db.add(pipeline_run)

        summary = RealForecastExecutionSummary(
            run_id=run_uuid,
            status="RUNNING",
            pipeline_run_id=None,
            total_companies=len(companies),
            total_forecasts_generated=0,
            total_forecasts_persisted=0,
            total_forecasts_unchanged=0,
        )

        forecasts_to_persist: List[Forecast] = []

        try:
            if pipeline_run:
                self.db.flush()
                summary.pipeline_run_id = pipeline_run.id

            for company in companies:
                symbol = company.symbol
                summary.symbols_processed.append(symbol)

                # Load OHLCV history
                history = load_company_ohlcv_history(self.db, company.id)
                if len(history) < 30:
                    raise RealForecastingError(
                        f"Insufficient OHLCV history for {symbol}: found {len(history)} records, need >= 30"
                    )

                # Load and verify artifacts for this symbol
                loaded_artifacts: List[Tuple[object, ProductionModelMetadata]] = []
                for m_code in model_codes:
                    norm_code = _normalize_model_code(m_code)
                    if (symbol, norm_code) not in entries_by_key:
                        raise RealForecastingError(f"Manifest has no entry for {symbol}/{norm_code}")
                    runtime_artifact = load_runtime_artifact(
                        bundle_root=bundle_dir,
                        symbol=symbol,
                        model_code=norm_code,
                        expected_version=bundle_version,
                        expected_manifest_sha256=manifest_sha,
                    )
                    model_obj, art_meta = runtime_artifact.model, runtime_artifact.metadata
                    meta_symbol = art_meta.get("symbol") if isinstance(art_meta, dict) else art_meta.symbol
                    meta_code = art_meta.get("model_code") if isinstance(art_meta, dict) else art_meta.model_code
                    if meta_symbol != symbol:
                        raise RealForecastingError(
                            f"Artifact symbol mismatch: artifact is for {meta_symbol}, expected {symbol}"
                        )
                    if _normalize_model_code(meta_code) != norm_code:
                        raise RealForecastingError(
                            f"Artifact model code mismatch: artifact is {meta_code}, expected {norm_code}"
                        )
                    loaded_artifacts.append((model_obj, art_meta))

                # Build loaded artifact lookup by normalized code
                artifact_meta_by_code: Dict[str, ProductionModelMetadata | dict] = {
                    _normalize_model_code(meta.get("model_code") if isinstance(meta, dict) else meta.model_code): meta
                    for _, meta in loaded_artifacts
                }

                # Run causal next-day inference
                company_forecast = predict_next_day_with_artifacts(
                    symbol=symbol,
                    records=history,
                    loaded_artifacts=loaded_artifacts,
                    calendar=self.calendar,
                )

                for pred in company_forecast.predictions:
                    norm_code = _normalize_model_code(pred.model)
                    meta_record = model_meta_map[norm_code]
                    art_meta = artifact_meta_by_code[norm_code]

                    # Inference requires prior explicit activation and never writes artifact lineage.
                    entry = entries_by_key[(symbol, norm_code)]
                    active_rows = self.db.query(ModelArtifact).filter(
                        ModelArtifact.company_id == company.id,
                        ModelArtifact.model_metadata_id == meta_record.id,
                        ModelArtifact.is_active.is_(True),
                    ).all()
                    if len(active_rows) != 1:
                        raise RealForecastingError(
                            f"Expected exactly one active artifact for {symbol}/{norm_code}, found {len(active_rows)}"
                        )
                    db_artifact = active_rows[0]
                    runtime_metadata = art_meta if isinstance(art_meta, dict) else art_meta.as_dict()
                    expected_lineage = {
                        "bundle_version": bundle_version,
                        "artifact_format": entry["artifact_format"],
                        "artifact_path": entry["artifact_relative_path"],
                        "artifact_sha256": entry["artifact_sha256"],
                        "trained_through": date.fromisoformat(entry["trained_through"]),
                        "data_row_count": entry["data_row_count"],
                        "source_repository": runtime_metadata["source_repository"],
                        "source_commit": runtime_metadata["source_commit"],
                        "historical_data_source_repository": runtime_metadata["historical_data_source_repository"],
                        "historical_data_source_commit": runtime_metadata["historical_data_source_commit"],
                    }
                    if any(getattr(db_artifact, key) != value for key, value in expected_lineage.items()):
                        raise RealForecastIntegrityError(f"Active ModelArtifact lineage mismatch for {symbol}/{norm_code}")

                    incoming_price = Decimal(str(round(pred.predicted_close, 4)))
                    incoming_delta = Decimal(str(round(pred.predicted_delta, 4)))

                    # Check for existing real forecasts
                    existing_real_fcs = (
                        self.db.query(Forecast)
                        .filter(
                            Forecast.company_id == company.id,
                            Forecast.model_id == meta_record.id,
                            Forecast.target_date == pred.forecast_for,
                            Forecast.is_demo == False,
                        )
                        .all()
                    )

                    if existing_real_fcs:
                        is_identical = False
                        for existing in existing_real_fcs:
                            same_artifact = (existing.model_artifact_id == db_artifact.id)
                            same_origin = (existing.origin_date == pred.origin_date)
                            same_target = (existing.target_date == pred.forecast_for)
                            same_price = (Decimal(str(round(float(existing.predicted_price), 4))) == incoming_price)
                            same_delta = (
                                Decimal(str(round(float(existing.predicted_delta), 4))) == incoming_delta
                                if existing.predicted_delta is not None
                                else incoming_delta is None
                            )

                            if same_artifact and same_origin and same_target and same_price and same_delta:
                                is_identical = True
                                logger.info(
                                    "Forecast already exists and is identical for %s (%s) on %s. Status: UNCHANGED.",
                                    symbol,
                                    norm_code,
                                    pred.forecast_for,
                                )
                                summary.total_forecasts_unchanged += 1
                                summary.items.append(
                                    ForecastItemSummary(
                                        symbol=symbol,
                                        model_code=norm_code,
                                        origin_date=pred.origin_date,
                                        target_date=pred.forecast_for,
                                        predicted_close=float(existing.predicted_price),
                                        predicted_delta=float(existing.predicted_delta) if existing.predicted_delta is not None else 0.0,
                                        lower_bound=float(existing.lower_bound) if existing.lower_bound is not None else None,
                                        upper_bound=float(existing.upper_bound) if existing.upper_bound is not None else None,
                                        artifact_id=db_artifact.id if db_artifact else "",
                                        status="UNCHANGED",
                                    )
                                )
                                break
                            else:
                                raise RealForecastIntegrityError(
                                    f"Real forecast integrity violation for {symbol} ({norm_code}) target {pred.forecast_for}: "
                                    f"existing forecast (artifact={existing.model_artifact_id}, origin={existing.origin_date}, "
                                    f"price={existing.predicted_price}, delta={existing.predicted_delta}) differs from incoming "
                                    f"(artifact={db_artifact.id}, origin={pred.origin_date}, price={incoming_price}, delta={incoming_delta}). "
                                    "Overwrites are forbidden on audited real forecasts."
                                )

                        if is_identical:
                            continue

                    new_fc = Forecast(
                        company_id=company.id,
                        model_id=meta_record.id,
                        model_artifact_id=db_artifact.id if db_artifact else None,
                        pipeline_run_id=pipeline_run.id if pipeline_run else None,
                        origin_date=pred.origin_date,
                        target_date=pred.forecast_for,
                        predicted_price=incoming_price,
                        predicted_delta=incoming_delta,
                        lower_bound=None,
                        upper_bound=None,
                        confidence_level=0.95,
                        is_demo=False,
                    )
                    if not dry_run:
                        self.db.add(new_fc)
                    forecasts_to_persist.append(new_fc)

                    summary.total_forecasts_generated += 1
                    summary.items.append(
                        ForecastItemSummary(
                            symbol=symbol,
                            model_code=norm_code,
                            origin_date=pred.origin_date,
                            target_date=pred.forecast_for,
                            predicted_close=pred.predicted_close,
                            predicted_delta=pred.predicted_delta,
                            lower_bound=None,
                            upper_bound=None,
                            artifact_id=db_artifact.id if db_artifact else "",
                            status="PERSISTED",
                        )
                    )

            if not dry_run:
                # Complete the audit row and forecasts in one transaction.
                if pipeline_run:
                    pipeline_run.status = "COMPLETED"
                    pipeline_run.completed_at = datetime.now(timezone.utc)
                    pipeline_run.forecasts_generated = len(forecasts_to_persist)
                self.db.flush()
                self.db.commit()
                summary.total_forecasts_persisted = len(forecasts_to_persist)
            else:
                summary.total_forecasts_persisted = 0
                logger.info("Dry-run complete: 0 database mutations committed.")

            summary.status = "COMPLETED"
            return summary

        except Exception as exc:
            logger.error("Real forecasting batch failed: %s", exc, exc_info=True)
            summary.status = "FAILED"
            summary.errors.append(str(exc))
            # Atomic rollback of all mutations
            self.db.rollback()

            if not dry_run and pipeline_run:
                try:
                    # Rollback removes the RUNNING row; create the failure audit
                    # explicitly in a fresh transaction using the same run ID.
                    failed_run = PipelineRun(
                        run_id=run_uuid,
                        status="FAILED",
                        started_at=now_utc,
                        completed_at=datetime.now(timezone.utc),
                        records_ingested=0,
                        forecasts_generated=0,
                        error_message=str(exc),
                        is_demo_run=False,
                    )
                    self.db.add(failed_run)
                    self.db.commit()
                except Exception as inner_exc:
                    logger.error("Failed to update PipelineRun status: %s", inner_exc)
                    self.db.rollback()

            if isinstance(exc, RealForecastingError):
                raise exc
            raise RealForecastingError(f"Real forecasting execution aborted: {exc}") from exc
