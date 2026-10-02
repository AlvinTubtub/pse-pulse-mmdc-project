"""Pipeline status Pydantic schemas."""

from datetime import datetime
from typing import Optional, List
from backend.app.schemas.common import BaseSchema


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
