"""Database persistence and storage snapshot scaffold for pipeline runs."""

from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import logging

from backend.app.models.pipeline_run import PipelineRun
from backend.app.models.forecast import Forecast
from backend.app.models.model_metadata import ModelMetadata
from backend.app.models.company import Company
from backend.app.models.price import DailyPrice
from backend.app.models.market_data_import import MarketDataImport
from backend.app.forecasting.base import InferencePoint
from backend.pipeline.ingest.models import EODQuote, ImportSummary

logger = logging.getLogger(__name__)


def _dec_match(a: Any, b: Any, precision: str = "0.0001") -> bool:
    """Compare two numeric values up to specified precision."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        da = Decimal(str(a)).quantize(Decimal(precision))
        db = Decimal(str(b)).quantize(Decimal(precision))
        return da == db
    except (InvalidOperation, ValueError, TypeError):
        return str(a) == str(b)


class DatabaseSaver:
    """Handles persisting pipeline execution outputs to PostgreSQL / SQLite."""

    def __init__(self, db: Session):
        self.db = db

    def create_run_record(self, is_demo: bool = True) -> PipelineRun:
        """Initialize a new PipelineRun record."""
        run = PipelineRun(
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            is_demo_run=is_demo,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finish_run_record(
        self,
        run_id: str,
        status: str,
        records_ingested: int = 0,
        forecasts_generated: int = 0,
        error_message: str | None = None,
    ) -> PipelineRun | None:
        """Mark a pipeline run as completed or failed."""
        run = self.db.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
        if not run:
            return None

        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        run.records_ingested = records_ingested
        run.forecasts_generated = forecasts_generated
        run.error_message = error_message

        self.db.commit()
        self.db.refresh(run)
        return run

    def persist_forecasts(
        self,
        company_id: int,
        model_forecasts: Dict[str, List[InferencePoint]],
        pipeline_run_id: int | None = None,
    ) -> int:
        """Persist generated forecasts into database."""
        count = 0
        for code, points in model_forecasts.items():
            model_meta = self.db.query(ModelMetadata).filter(ModelMetadata.code == code).first()
            if not model_meta:
                continue

            for pt in points:
                # Check for existing record on company_id, model_id, target_date, pipeline_run_id
                existing = (
                    self.db.query(Forecast)
                    .filter(
                        Forecast.company_id == company_id,
                        Forecast.model_id == model_meta.id,
                        Forecast.target_date == pt.target_date,
                        Forecast.pipeline_run_id == pipeline_run_id,
                    )
                    .first()
                )

                if existing:
                    existing.predicted_price = pt.predicted_price
                    existing.lower_bound = pt.lower_bound
                    existing.upper_bound = pt.upper_bound
                    existing.confidence_level = pt.confidence_level
                    existing.is_demo = pt.is_demo
                else:
                    new_fc = Forecast(
                        company_id=company_id,
                        model_id=model_meta.id,
                        pipeline_run_id=pipeline_run_id,
                        target_date=pt.target_date,
                        predicted_price=pt.predicted_price,
                        lower_bound=pt.lower_bound,
                        upper_bound=pt.upper_bound,
                        confidence_level=pt.confidence_level,
                        is_demo=pt.is_demo,
                    )
                    self.db.add(new_fc)
                count += 1

        self.db.commit()
        return count

    def persist_daily_prices(
        self,
        quotes: List[EODQuote],
        sha256_hash: str = "",
        source_filename: str = "",
        dry_run: bool = False,
        commit: bool = True,
        records_seen: Optional[int] = None,
        records_rejected: int = 0,
    ) -> ImportSummary:
        """Persist normalized EOD quotes to daily_prices table with idempotency.

        Rules:
        - Only active tracked companies (Company.is_active == True) are stored in daily_prices.
        - Untracked equities are counted as records_untracked.
        - If (company_id, trade_date) already exists with identical OHLCV, counted as unchanged.
        - If (company_id, trade_date) already exists with different OHLCV, values are updated.
        - If new, a new DailyPrice row is inserted.
        - If dry_run is True, transactions are rolled back; zero DB mutations occur.
        - If commit is False, changes are staged/flushed in session for atomic multi-entity commit.
        - Database write errors are NOT swallowed; they rollback and re-raise to caller.
        """
        active_companies = (
            self.db.query(Company)
            .filter(Company.is_active == True)
            .all()
        )
        company_map = {c.symbol.upper(): c for c in active_companies}

        trade_dt = quotes[0].trade_date if quotes else None
        fname = source_filename or (quotes[0].source_filename if quotes and quotes[0].source_filename else "UNKNOWN")

        total_seen = records_seen if records_seen is not None else (len(quotes) + records_rejected)
        total_valid = len(quotes)

        records_tracked = 0
        records_untracked = 0
        records_inserted = 0
        records_updated = 0
        records_unchanged = 0

        try:
            for quote in quotes:
                sym = quote.symbol.strip().upper()
                if sym not in company_map:
                    records_untracked += 1
                    continue

                comp = company_map[sym]
                records_tracked += 1

                existing = (
                    self.db.query(DailyPrice)
                    .filter(
                        DailyPrice.company_id == comp.id,
                        DailyPrice.trade_date == quote.trade_date,
                    )
                    .first()
                )

                if existing:
                    # Compare OHLCV
                    is_same = (
                        _dec_match(existing.open_price, quote.open_price)
                        and _dec_match(existing.high_price, quote.high_price)
                        and _dec_match(existing.low_price, quote.low_price)
                        and _dec_match(existing.close_price, quote.close_price)
                        and int(existing.volume) == int(quote.volume)
                    )
                    if quote.value is not None and existing.value is not None:
                        is_same = is_same and _dec_match(existing.value, quote.value, "0.01")

                    if is_same:
                        records_unchanged += 1
                    else:
                        if not dry_run:
                            existing.open_price = quote.open_price
                            existing.high_price = quote.high_price
                            existing.low_price = quote.low_price
                            existing.close_price = quote.close_price
                            existing.volume = quote.volume
                            existing.value = quote.value
                        records_updated += 1
                else:
                    if not dry_run:
                        new_record = DailyPrice(
                            company_id=comp.id,
                            trade_date=quote.trade_date,
                            open_price=quote.open_price,
                            high_price=quote.high_price,
                            low_price=quote.low_price,
                            close_price=quote.close_price,
                            volume=quote.volume,
                            value=quote.value,
                        )
                        self.db.add(new_record)
                    records_inserted += 1

            if dry_run:
                self.db.rollback()
                status = "DRY_RUN"
            elif commit:
                self.db.commit()
                status = "COMPLETED"
            else:
                self.db.flush()
                status = "COMPLETED"

            return ImportSummary(
                trade_date=trade_dt,
                source_filename=fname,
                sha256=sha256_hash,
                status=status,
                records_seen=total_seen,
                records_tracked=records_tracked,
                records_valid=total_valid,
                records_rejected=records_rejected,
                records_inserted=records_inserted,
                records_updated=records_updated,
                records_unchanged=records_unchanged,
                records_untracked=records_untracked,
            )

        except Exception as e:
            self.db.rollback()
            logger.error("Failed to persist daily prices: %s", e, exc_info=True)
            raise

    def record_market_data_import(
        self,
        summary: ImportSummary,
        commit: bool = True,
    ) -> MarketDataImport:
        """Record provenance audit log in market_data_imports table.

        If commit=False, stages record into existing session transaction for atomic commit.
        """
        try:
            record = MarketDataImport(
                source_type="PSE_DQR_FILE",
                source_filename=summary.source_filename,
                trade_date=summary.trade_date,
                sha256=summary.sha256,
                imported_at=datetime.now(timezone.utc),
                status=summary.status,
                records_seen=summary.records_seen,
                records_valid=summary.records_valid,
                records_inserted=summary.records_inserted,
                records_updated=summary.records_updated,
                records_rejected=summary.records_rejected,
                error_message=summary.error_message,
            )
            self.db.add(record)
            if commit:
                self.db.commit()
                self.db.refresh(record)
            else:
                self.db.flush()
            return record
        except Exception as e:
            self.db.rollback()
            logger.error("Failed to record market data import: %s", e, exc_info=True)
            raise

    def record_failed_import(
        self,
        source_filename: str,
        sha256: str,
        trade_date: Optional[date] = None,
        records_seen: int = 0,
        records_valid: int = 0,
        records_rejected: int = 0,
        error_message: Optional[str] = None,
    ) -> Optional[MarketDataImport]:
        """Record an operational FAILED import provenance audit entry in its own isolated transaction."""
        try:
            record = MarketDataImport(
                source_type="PSE_DQR_FILE",
                source_filename=source_filename,
                trade_date=trade_date,
                sha256=sha256,
                imported_at=datetime.now(timezone.utc),
                status="FAILED",
                records_seen=records_seen,
                records_valid=records_valid,
                records_inserted=0,
                records_updated=0,
                records_rejected=records_rejected,
                error_message=error_message,
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            return record
        except Exception as e:
            self.db.rollback()
            logger.warning("Could not persist failed import provenance audit record: %s", e)
            return None

    def get_import_by_sha256(self, sha256_hash: str) -> Optional[MarketDataImport]:
        """Find any previous completed import with this SHA-256 checksum."""
        if not sha256_hash:
            return None
        return (
            self.db.query(MarketDataImport)
            .filter(
                MarketDataImport.sha256 == sha256_hash,
                MarketDataImport.status == "COMPLETED",
            )
            .order_by(MarketDataImport.imported_at.desc())
            .first()
        )

    def get_last_market_data_import(self) -> Optional[MarketDataImport]:
        """Fetch the most recent market data import record."""
        return (
            self.db.query(MarketDataImport)
            .order_by(MarketDataImport.imported_at.desc())
            .first()
        )
