"""Reader and validator for official repository raw OHLCV CSV files.

Parses official CSVs (e.g. ALI.csv, SMPH.csv) with strict schema validation,
financial sanity rules, SHA-256 computation, and in-memory normalization.
"""

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import math
from pathlib import Path
from typing import List, Tuple, Set, Final

from backend.pipeline.bootstrap.models import HistoricalQuote

REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
)


class HistoricalCsvValidationError(ValueError):
    """Raised when an official historical CSV violates schema or financial rules."""


class OfficialRepoHistoricalProvider:
    """Parses and validates official historical OHLCV CSV files."""

    def __init__(self):
        pass

    @staticmethod
    def calculate_file_sha256(file_path: Path) -> str:
        """Compute SHA-256 cryptographic hash of a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def parse_file(self, file_path: Path, expected_symbol: str) -> Tuple[List[HistoricalQuote], str]:
        """Read and validate quotes from an official CSV file.

        Args:
            file_path: Path to the raw CSV file.
            expected_symbol: Configured symbol (e.g. 'SMPH').

        Returns:
            Tuple of (list of validated HistoricalQuote objects, sha256_hash).

        Raises:
            HistoricalCsvValidationError on schema mismatch, invalid numbers, or duplicate dates.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Historical file not found: {file_path}")

        sha256_hash = self.calculate_file_sha256(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames

            if not fieldnames:
                raise HistoricalCsvValidationError(f"File {file_path.name} is empty or missing headers")

            missing_cols = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
            if missing_cols:
                raise HistoricalCsvValidationError(
                    f"File {file_path.name} missing required columns: {', '.join(missing_cols)}"
                )

            quotes: List[HistoricalQuote] = []
            seen_dates: Set[date] = set()

            for row_idx, row in enumerate(reader, start=2):
                quote = self._parse_row(row, row_idx=row_idx, symbol=expected_symbol, filename=file_path.name)
                if quote.trade_date in seen_dates:
                    raise HistoricalCsvValidationError(
                        f"File {file_path.name} row {row_idx}: Duplicate trade date {quote.trade_date}"
                    )
                seen_dates.add(quote.trade_date)
                quotes.append(quote)

        if not quotes:
            raise HistoricalCsvValidationError(f"File {file_path.name} contains zero data rows")

        # Verify chronological order
        sorted_quotes = sorted(quotes, key=lambda q: q.trade_date)
        if quotes != sorted_quotes:
            raise HistoricalCsvValidationError(
                f"File {file_path.name}: Rows are not in strict chronological order"
            )

        return quotes, sha256_hash

    def _parse_row(
        self,
        row: dict,
        row_idx: int,
        symbol: str,
        filename: str,
    ) -> HistoricalQuote:
        date_str = (row.get("Date") or "").strip()
        if not date_str:
            raise HistoricalCsvValidationError(f"{filename} row {row_idx}: Missing Date value")

        try:
            trade_date = date.fromisoformat(date_str)
        except ValueError as e:
            raise HistoricalCsvValidationError(
                f"{filename} row {row_idx}: Invalid Date format '{date_str}': {e}"
            ) from e

        # Validate & parse prices
        open_d = self._parse_price(row.get("Open"), "Open", row_idx, filename)
        high_d = self._parse_price(row.get("High"), "High", row_idx, filename)
        low_d = self._parse_price(row.get("Low"), "Low", row_idx, filename)
        close_d = self._parse_price(row.get("Close"), "Close", row_idx, filename)

        # OHLC relationships
        if high_d < max(open_d, close_d, low_d):
            raise HistoricalCsvValidationError(
                f"{filename} row {row_idx} ({trade_date}): High ({high_d}) cannot be below Open ({open_d}), Close ({close_d}), or Low ({low_d})"
            )
        if low_d > min(open_d, close_d, high_d):
            raise HistoricalCsvValidationError(
                f"{filename} row {row_idx} ({trade_date}): Low ({low_d}) cannot be above Open ({open_d}), Close ({close_d}), or High ({high_d})"
            )

        # Volume validation: finite, non-negative Decimal parsed directly from source string
        vol_raw = (row.get("Volume") or "").strip()
        if not vol_raw:
            raise HistoricalCsvValidationError(f"{filename} row {row_idx}: Missing Volume value")

        try:
            vol_d = Decimal(vol_raw)
        except InvalidOperation as e:
            raise HistoricalCsvValidationError(
                f"{filename} row {row_idx}: Volume is not a valid decimal number '{vol_raw}'"
            ) from e

        if vol_d.is_nan() or vol_d.is_infinite():
            raise HistoricalCsvValidationError(
                f"{filename} row {row_idx}: Volume must be finite (got '{vol_raw}')"
            )
        if vol_d < 0:
            raise HistoricalCsvValidationError(
                f"{filename} row {row_idx}: Volume cannot be negative (got {vol_d})"
            )

        return HistoricalQuote(
            symbol=symbol,
            trade_date=trade_date,
            open_price=open_d,
            high_price=high_d,
            low_price=low_d,
            close_price=close_d,
            volume=vol_d,
        )

    def _parse_price(self, val: object, col: str, row_idx: int, filename: str) -> Decimal:
        raw = str(val).strip() if val is not None else ""
        if not raw:
            raise HistoricalCsvValidationError(f"{filename} row {row_idx}: {col} price is blank")
        try:
            d = Decimal(raw)
        except InvalidOperation as e:
            raise HistoricalCsvValidationError(
                f"{filename} row {row_idx}: {col} price is not numeric '{raw}'"
            ) from e

        if d.is_nan() or d.is_infinite():
            raise HistoricalCsvValidationError(
                f"{filename} row {row_idx}: {col} price must be finite, got '{raw}'"
            )
        if d <= 0:
            raise HistoricalCsvValidationError(
                f"{filename} row {row_idx}: {col} price must be strictly positive (> 0), got {d}"
            )
        return d
