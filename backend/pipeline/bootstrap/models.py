"""Data models for official repository historical OHLCV bootstrap."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional, List


@dataclass(frozen=True, slots=True)
class HistoricalQuote:
    """Validated normalized daily market quote from official historical repository."""

    symbol: str
    trade_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    value: Optional[Decimal] = None


@dataclass(slots=True)
class SymbolBootstrapResult:
    """Outcome of historical bootstrap for a single equity symbol."""

    symbol: str
    source_filename: str
    sha256: str
    first_trade_date: Optional[date]
    last_trade_date: Optional[date]
    rows_seen: int = 0
    rows_valid: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_unchanged: int = 0
    status: str = "COMPLETED"
    error_message: Optional[str] = None


@dataclass(slots=True)
class BootstrapSummary:
    """Comprehensive summary of the 15-company historical bootstrap session."""

    total_symbols: int = 0
    total_rows_seen: int = 0
    total_rows_valid: int = 0
    total_rows_inserted: int = 0
    total_rows_updated: int = 0
    total_rows_unchanged: int = 0
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None
    status: str = "COMPLETED"
    symbol_results: List[SymbolBootstrapResult] = field(default_factory=list)
    error_message: Optional[str] = None
