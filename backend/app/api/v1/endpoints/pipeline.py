"""Pipeline status endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.config import get_settings, Settings
from backend.app.database import get_db
from backend.app.models.pipeline_run import PipelineRun
from backend.app.models.market_data_import import MarketDataImport
from backend.app.schemas.pipeline import (
    PipelineStatusResponse,
    PipelineRunRead,
    MarketDataImportRead,
)

router = APIRouter()


@router.get("/status", response_model=PipelineStatusResponse)
def get_pipeline_status(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    """Retrieve end-of-day market pipeline operational status."""
    recent_runs = (
        db.query(PipelineRun)
        .order_by(PipelineRun.started_at.desc())
        .limit(5)
        .all()
    )

    last_run_item = None
    if recent_runs:
        lr = recent_runs[0]
        last_run_item = PipelineRunRead(
            id=lr.id,
            run_id=lr.run_id,
            status=lr.status,
            started_at=lr.started_at,
            completed_at=lr.completed_at,
            records_ingested=lr.records_ingested,
            forecasts_generated=lr.forecasts_generated,
            error_message=lr.error_message,
            is_demo_run=lr.is_demo_run,
        )

    all_read = [
        PipelineRunRead(
            id=r.id,
            run_id=r.run_id,
            status=r.status,
            started_at=r.started_at,
            completed_at=r.completed_at,
            records_ingested=r.records_ingested,
            forecasts_generated=r.forecasts_generated,
            error_message=r.error_message,
            is_demo_run=r.is_demo_run,
        )
        for r in recent_runs
    ]

    # Query latest market data import provenance
    last_import = (
        db.query(MarketDataImport)
        .order_by(MarketDataImport.imported_at.desc())
        .first()
    )
    last_import_item = None
    if last_import:
        last_import_item = MarketDataImportRead(
            id=last_import.id,
            source_type=last_import.source_type,
            source_filename=last_import.source_filename,
            trade_date=last_import.trade_date,
            sha256=last_import.sha256,
            imported_at=last_import.imported_at,
            status=last_import.status,
            records_seen=last_import.records_seen,
            records_valid=last_import.records_valid,
            records_inserted=last_import.records_inserted,
            records_updated=last_import.records_updated,
            records_rejected=last_import.records_rejected,
            error_message=last_import.error_message,
        )

    return PipelineStatusResponse(
        status="idle" if not recent_runs or recent_runs[0].status == "COMPLETED" else "active",
        schedule="0 18 * * 1-5 (Weekdays 18:00 PHT)",
        is_demo_mode=settings.DEMO_MODE,
        last_run=last_run_item,
        last_market_data_import=last_import_item,
        recent_runs=all_read,
    )
