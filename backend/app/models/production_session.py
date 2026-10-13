"""Auditable trading-session state for strict production orchestration."""

from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, String, Text
from backend.app.database import Base


class ProductionSession(Base):
    __tablename__ = "production_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('NON_TRADING', 'PENDING_SOURCE', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_production_sessions_status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, unique=True, nullable=False)
    status = Column(String(24), nullable=False, index=True)
    calendar_sha256 = Column(String(64), nullable=False)
    source_sha256 = Column(String(64), nullable=True)
    source_manifest_sha256 = Column(String(64), nullable=True)
    source_url = Column(String(500), nullable=True)
    source_reviewer = Column(String(120), nullable=True)
    market_data_import_id = Column(Integer, ForeignKey("market_data_imports.id"), nullable=True)
    model_bundle_version = Column(String(50), nullable=True)
    model_manifest_sha256 = Column(String(64), nullable=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"), nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
