"""Pipeline run execution tracking model."""

from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from backend.app.database import Base


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    status = Column(String(20), nullable=False, default="PENDING", index=True)  # PENDING, RUNNING, COMPLETED, FAILED
    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    records_ingested = Column(Integer, default=0, nullable=False)
    forecasts_generated = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    is_demo_run = Column(Boolean, default=True, nullable=False)
