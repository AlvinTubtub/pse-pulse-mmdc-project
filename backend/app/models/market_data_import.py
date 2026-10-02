"""Market data import provenance SQLAlchemy model."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Text,
)
from backend.app.database import Base


class MarketDataImport(Base):
    __tablename__ = "market_data_imports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source_type = Column(String(64), nullable=False, default="PSE_DQR_FILE")
    source_filename = Column(String(255), nullable=False)
    trade_date = Column(Date, nullable=True, index=True)
    sha256 = Column(String(64), nullable=False, index=True)
    imported_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status = Column(String(32), nullable=False, default="COMPLETED")
    records_seen = Column(Integer, nullable=False, default=0)
    records_valid = Column(Integer, nullable=False, default=0)
    records_inserted = Column(Integer, nullable=False, default=0)
    records_updated = Column(Integer, nullable=False, default=0)
    records_rejected = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)


