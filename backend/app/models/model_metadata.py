"""Model metadata SQLAlchemy model."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.database import Base


class ModelMetadata(Base):
    __tablename__ = "model_metadata"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False, index=True)
    version = Column(String(30), nullable=False, default="0.1.0-stub")
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    forecasts = relationship("Forecast", back_populates="model_metadata")

    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_model_code_version"),
    )
