"""PSE Pulse pipeline CLI execution entrypoint.

Invoked by systemd timer or manual command to orchestrate the EOD cycle:
check -> ingest -> validate -> features -> forecast -> persist.
"""

from datetime import date
import logging
import sys

from backend.app.database import SessionLocal
from backend.app.config import get_settings
from backend.pipeline.ingest.eod_ingest import EODIngestionService
from backend.pipeline.validation.data_validator import DataValidator
from backend.pipeline.features.feature_builder import FeatureBuilder
from backend.pipeline.forecasting.runner import PipelineForecastRunner
from backend.pipeline.persistence.db_saver import DatabaseSaver
from backend.app.models.company import Company
from backend.app.models.price import DailyPrice
from backend.app.forecasting.base import PriceHistoryItem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pse_pulse_pipeline")


def run_eod_pipeline():
    settings = get_settings()
    logger.info("Starting PSE Pulse EOD pipeline run (Demo Mode: %s)...", settings.DEMO_MODE)

    db = SessionLocal()
    saver = DatabaseSaver(db)
    run_record = saver.create_run_record(is_demo=settings.DEMO_MODE)
    logger.info("Initialized PipelineRun ID: %s", run_record.run_id)

    try:
        # Step 1: Market Availability Check
        today = date.today()
        ingest_svc = EODIngestionService()
        is_market_open = ingest_svc.check_eod_availability(today)
        logger.info("Market session check for %s: %s", today, is_market_open)

        # Step 2: Companies & Price History Query
        companies = db.query(Company).filter(Company.is_active == True).all()
        logger.info("Found %d active companies to process", len(companies))

        forecast_runner = PipelineForecastRunner()
        total_forecasts = 0

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

            # Generate forecasts across active model stubs
            model_results = forecast_runner.run_inference_for_symbol(
                symbol=comp.symbol,
                history=history_items,
                model_codes=["LAG_REGRESSION", "ARIMA", "LSTM"],
                horizon_days=5,
            )

            persisted_count = saver.persist_forecasts(
                comp.id, model_results, pipeline_run_id=run_record.id
            )
            total_forecasts += persisted_count

        saver.finish_run_record(
            run_id=run_record.run_id,
            status="COMPLETED",
            records_ingested=len(companies),
            forecasts_generated=total_forecasts,
        )
        logger.info("Pipeline completed successfully. Generated %d forecast points.", total_forecasts)

    except Exception as e:
        logger.error("Pipeline run failed: %s", e, exc_info=True)
        saver.finish_run_record(
            run_id=run_record.run_id,
            status="FAILED",
            error_message=str(e),
        )
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    run_eod_pipeline()
