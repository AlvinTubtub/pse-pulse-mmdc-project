"""PSE Pulse pipeline CLI execution entrypoint.

Orchestrates the End-of-Day market data cycle:
file discovery/load -> SHA-256 deduplication -> parsing -> validation ->
persistence (idempotent upsert) -> provenance audit logging ->
features & forecasting (in demo mode).
"""

import argparse
from datetime import date
import logging
from pathlib import Path
import sys
from typing import Optional, List
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.config import get_settings
from backend.pipeline.ingest.eod_ingest import EODIngestionService
from backend.pipeline.validation.data_validator import DataValidator
from backend.pipeline.forecasting.runner import PipelineForecastRunner
from backend.pipeline.persistence.db_saver import DatabaseSaver
from backend.app.models.company import Company
from backend.app.models.price import DailyPrice
from backend.app.forecasting.base import PriceHistoryItem
from backend.pipeline.ingest.models import ImportSummary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pse_pulse_pipeline")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        description="PSE Pulse End-of-Day (EOD) Ingestion and Forecast Pipeline"
    )
    parser.add_argument(
        "--source-file",
        type=Path,
        default=None,
        help="Path to official PSE Daily Quotation Report file (PDF or text)",
    )
    parser.add_argument(
        "--trade-date",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="Expected trade date in YYYY-MM-DD format for verification",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate file, simulate persistence without committing changes",
    )
    parser.add_argument(
        "--ingest-only",
        action="store_true",
        help="Run ingestion and persistence only; skip feature and forecasting steps",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow re-importing a file even if its SHA-256 was previously imported",
    )
    return parser


def find_incoming_file() -> Optional[Path]:
    """Look for candidate market report in data/incoming/ directory."""
    incoming_dir = Path("data/incoming")
    if not incoming_dir.exists() or not incoming_dir.is_dir():
        return None

    # Check for supported extensions
    candidates: List[Path] = []
    for ext in ("*.pdf", "*.txt", "*.csv"):
        candidates.extend(incoming_dir.glob(ext))

    if not candidates:
        return None

    # Return most recently modified file
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def run_pipeline(
    source_file: Optional[Path] = None,
    trade_date: Optional[date] = None,
    dry_run: bool = False,
    ingest_only: bool = False,
    force: bool = False,
    db: Optional[Session] = None,
) -> int:
    """Execute the PSE Pulse pipeline."""
    settings = get_settings()
    logger.info(
        "Starting PSE Pulse pipeline (Environment: %s, Demo Mode: %s, Dry Run: %s)...",
        settings.ENVIRONMENT,
        settings.DEMO_MODE,
        dry_run,
    )

    # Determine source file
    active_source = source_file
    if active_source is None:
        active_source = find_incoming_file()
        if active_source:
            logger.info("Discovered incoming market report: %s", active_source)

    close_db_on_exit = False
    if db is None:
        db = SessionLocal()
        close_db_on_exit = True
    saver = DatabaseSaver(db)
    run_record = None
    if not dry_run:
        run_record = saver.create_run_record(is_demo=settings.DEMO_MODE)
        logger.info("Initialized PipelineRun ID: %s", run_record.run_id)

    total_ingested = 0
    total_forecasts = 0
    import_summary: Optional[ImportSummary] = None

    try:
        # Step 1: Market Availability & Ingestion
        ingest_svc = EODIngestionService()
        validator = DataValidator()

        if active_source is not None:
            source_path = Path(active_source)
            logger.info("Processing source market data file: %s", source_path)

            try:
                raw_quotes, sha256_hash = ingest_svc.ingest_from_file(
                    source_file=source_path,
                    target_date=trade_date,
                    force=force,
                    db=db if not dry_run else None,
                )
            except ValueError as ve:
                if "already successfully imported" in str(ve).lower():
                    logger.warning(
                        "Source file '%s' was ALREADY_IMPORTED / SKIPPED. "
                        "Preserving idempotency without duplicating records. Use --force to re-import.",
                        source_path.name,
                    )
                    if not dry_run and run_record:
                        saver.finish_run_record(
                            run_id=run_record.run_id,
                            status="COMPLETED",
                            records_ingested=0,
                            forecasts_generated=0,
                        )
                    return 0
                raise

            logger.info("Loaded %d raw quotes from file", len(raw_quotes))

            # Step 2: Financial Validation & Deduplication
            valid_quotes, invalid_records = validator.validate_dataset(
                records=raw_quotes,
                target_date=trade_date,
            )
            logger.info(
                "Validation summary: %d valid quotes, %d invalid/rejected",
                len(valid_quotes),
                len(invalid_records),
            )

            # Step 3: Persistence to daily_prices
            import_summary = saver.persist_daily_prices(
                quotes=valid_quotes,
                sha256_hash=sha256_hash,
                source_filename=source_path.name,
                dry_run=dry_run,
            )
            import_summary.records_rejected = len(invalid_records)

            total_ingested = import_summary.records_inserted + import_summary.records_updated

            logger.info(
                "Persistence summary: seen=%d, tracked=%d, inserted=%d, updated=%d, unchanged=%d, untracked=%d",
                import_summary.records_seen,
                import_summary.records_tracked,
                import_summary.records_inserted,
                import_summary.records_updated,
                import_summary.records_unchanged,
                import_summary.records_untracked,
            )

            # Record provenance in market_data_imports
            if not dry_run:
                audit_record = saver.record_market_data_import(import_summary)
                logger.info(
                    "Recorded market data import audit entry ID: %d (SHA-256: %s...)",
                    audit_record.id,
                    audit_record.sha256[:12],
                )
        else:
            logger.info("No source file provided or detected in data/incoming. Ingestion step skipped.")

        # Step 4: Forecasting (Safety Guard: Only run stubs in Demo Mode)
        if not ingest_only:
            if settings.DEMO_MODE:
                logger.info("Demo Mode active: generating stub forecasts for tracked companies...")
                companies = db.query(Company).filter(Company.is_active == True).all()
                forecast_runner = PipelineForecastRunner()

                for comp in companies:
                    recent_prices = (
                        db.query(DailyPrice)
                        .filter(DailyPrice.company_id == comp.id)
                        .order_by(DailyPrice.trade_date.asc())
                        .all()
                    )

                    history_items = [
                        PriceHistoryItem(
                            trade_date=p.trade_date,
                            open_price=float(p.open_price),
                            high_price=float(p.high_price),
                            low_price=float(p.low_price),
                            close_price=float(p.close_price),
                            volume=p.volume,
                        )
                        for p in recent_prices
                    ]

                    model_results = forecast_runner.run_inference_for_symbol(
                        symbol=comp.symbol,
                        history=history_items,
                        model_codes=["LAG_REGRESSION", "ARIMA", "LSTM"],
                        horizon_days=5,
                    )

                    if not dry_run:
                        p_count = saver.persist_forecasts(
                            comp.id,
                            model_results,
                            pipeline_run_id=run_record.id if run_record else None,
                        )
                        total_forecasts += p_count
                    else:
                        total_forecasts += sum(len(pts) for pts in model_results.values())
            else:
                logger.info(
                    "Production safety rule: DEMO_MODE is False. Skipping stub forecast generation. "
                    "Only trained model artifacts will run in future phases."
                )
        else:
            logger.info("Ingest-only flag active: skipping downstream forecasting.")

        if not dry_run and run_record:
            saver.finish_run_record(
                run_id=run_record.run_id,
                status="COMPLETED",
                records_ingested=total_ingested,
                forecasts_generated=total_forecasts,
            )

        logger.info(
            "Pipeline finished successfully. Records ingested: %d, Forecasts generated: %d",
            total_ingested,
            total_forecasts,
        )
        return 0

    except Exception as e:
        logger.error("Pipeline run failed: %s", e, exc_info=True)
        if not dry_run and run_record:
            saver.finish_run_record(
                run_id=run_record.run_id,
                status="FAILED",
                error_message=str(e),
            )
        return 1
    finally:
        if close_db_on_exit and db:
            db.close()


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    exit_code = run_pipeline(
        source_file=args.source_file,
        trade_date=args.trade_date,
        dry_run=args.dry_run,
        ingest_only=args.ingest_only,
        force=args.force,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
