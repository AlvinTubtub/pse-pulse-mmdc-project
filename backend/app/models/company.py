"""Company SQLAlchemy model."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    sector_id = Column(Integer, ForeignKey("sectors.id"), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    listing_date = Column(Date, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    sector = relationship("Sector", back_populates="companies")
    daily_prices = relationship("DailyPrice", back_populates="company", cascade="all, delete-orphan")
    forecasts = relationship("Forecast", back_populates="company", cascade="all, delete-orphan")
