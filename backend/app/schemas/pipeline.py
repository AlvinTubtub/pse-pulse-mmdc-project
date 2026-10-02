"""Pipeline status Pydantic schemas."""

from datetime import datetime, date
from typing import Optional, List
from backend.app.schemas.common import BaseSchema


class MarketDataImportRead(BaseSchema):
    id: int
    source_type: str
    source_filename: str
    trade_date: Optional[date] = None
    sha256: str
    imported_at: datetime
    status: str
    records_seen: int
    records_valid: int
    records_inserted: int
    records_updated: int
    records_rejected: int
    records_unchanged: int = 0
    source_repository: Optional[str] = None
    source_commit: Optional[str] = None
    source_path: Optional[str] = None
    symbol: Optional[str] = None
    first_trade_date: Optional[date] = None
    last_trade_date: Optional[date] = None
    error_message: Optional[str] = None



class PipelineRunRead(BaseSchema):
    id: int
    run_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    records_ingested: int
    forecasts_generated: int
    error_message: Optional[str] = None
    is_demo_run: bool


class PipelineStatusResponse(BaseSchema):
    status: str
    schedule: str
    is_demo_mode: bool
    last_run: Optional[PipelineRunRead] = None
    last_market_data_import: Optional[MarketDataImportRead] = None
    recent_runs: List[PipelineRunRead] = []
    stages: List[str] = [
        "availability_check",
        "ingest",
        "validation",
        "features",
        "forecasting",
        "persistence",
        "blob_snapshot",
    ]
