"""Forecast SQLAlchemy model."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from backend.app.database import Base


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    model_id = Column(Integer, ForeignKey("model_metadata.id"), nullable=False, index=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True)
    target_date = Column(Date, nullable=False, index=True)
    predicted_price = Column(Numeric(12, 4), nullable=False)
    lower_bound = Column(Numeric(12, 4), nullable=True)
    upper_bound = Column(Numeric(12, 4), nullable=True)
    confidence_level = Column(Float, default=0.95, nullable=False)
    is_demo = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    company = relationship("Company", back_populates="forecasts")
    model_metadata = relationship("ModelMetadata", back_populates="forecasts")
    pipeline_run = relationship("PipelineRun", backref="forecasts")

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "model_id",
            "target_date",
            "pipeline_run_id",
            name="uq_forecast_company_model_date_run",
        ),
        Index("ix_forecasts_company_target_date", "company_id", "target_date"),
    )
