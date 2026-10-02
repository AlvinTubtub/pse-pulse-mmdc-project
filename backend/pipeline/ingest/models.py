"""Normalized models for market data ingestion."""

from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class EODQuote(BaseModel):
    """Normalized End-of-Day quote record extracted from an official source."""

    trade_date: date
    symbol: str = Field(min_length=1, max_length=20)
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal = Field(ge=0)
    value: Optional[Decimal] = None
    source: str = "PSE_DQR_FILE"
    security_name: Optional[str] = None
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    net_foreign: Optional[Decimal] = None
    source_filename: Optional[str] = None


class ImportSummary(BaseModel):
    """Structured summary of an ingestion operation."""

    trade_date: Optional[date] = None
    source_filename: str
    sha256: str
    status: str = "COMPLETED"  # COMPLETED, FAILED, ALREADY_IMPORTED, DRY_RUN
    records_seen: int = 0
    records_tracked: int = 0
    records_valid: int = 0
    records_rejected: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_unchanged: int = 0
    records_untracked: int = 0
    error_message: Optional[str] = None
