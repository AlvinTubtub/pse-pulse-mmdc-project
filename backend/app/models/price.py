"""Daily price SQLAlchemy model."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from backend.app.database import Base


class DailyPrice(Base):
    __tablename__ = "daily_prices"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    open_price = Column(Numeric(12, 4), nullable=False)
    high_price = Column(Numeric(12, 4), nullable=False)
    low_price = Column(Numeric(12, 4), nullable=False)
    close_price = Column(Numeric(12, 4), nullable=False)
    volume = Column(BigInteger, nullable=False, default=0)
    value = Column(Numeric(18, 4), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    company = relationship("Company", back_populates="daily_prices")

    __table_args__ = (
        UniqueConstraint("company_id", "trade_date", name="uq_company_trade_date"),
        Index("ix_daily_prices_company_date", "company_id", "trade_date"),
    )
