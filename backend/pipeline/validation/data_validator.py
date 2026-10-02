"""Data validation rules for PSE Pulse market data."""

from datetime import date
from decimal import Decimal, InvalidOperation
import math
import re
from typing import List, Dict, Any, Tuple, Optional, Union, Set
import logging

from backend.pipeline.ingest.models import EODQuote

logger = logging.getLogger(__name__)


class DataValidator:
    """Validates raw price feeds and normalized quotes against financial sanity constraints."""

    @staticmethod
    def _is_finite_number(val: Any) -> bool:
        """Check if value is a valid finite numeric value."""
        if val is None:
            return False
        if isinstance(val, (int, Decimal)):
            return True
        if isinstance(val, float):
            return not (math.isnan(val) or math.isinf(val))
        try:
            d = Decimal(str(val))
            return not (d.is_nan() or d.is_infinite())
        except (InvalidOperation, ValueError, TypeError):
            return False

    @staticmethod
    def _to_decimal(val: Any) -> Optional[Decimal]:
        """Safely convert value to Decimal."""
        if val is None:
            return None
        if isinstance(val, Decimal):
            if val.is_nan() or val.is_infinite():
                return None
            return val
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val):
                return None
            return Decimal(str(val))
        try:
            d = Decimal(str(val))
            if d.is_nan() or d.is_infinite():
                return None
            return d
        except (InvalidOperation, ValueError, TypeError):
            return None

    @classmethod
    def validate_ohlc_record(
        cls,
        record: Union[Dict[str, Any], EODQuote],
        target_date: Optional[date] = None,
    ) -> Tuple[bool, List[str]]:
        """Validate a single OHLC record or EODQuote.

        Rules:
        1. Required fields: open, high, low, close, volume (and symbol/trade_date if present).
        2. Finite numeric sanity: reject NaN, Infinity, -Infinity.
        3. Open, High, Low, Close must be strictly positive numbers (> 0).
        4. High must be >= Open, Close, and Low.
        5. Low must be <= Open, Close, and High.
        6. Volume must be >= 0.
        7. Value (if present) must be >= 0.
        8. Target date consistency: if target_date provided, trade_date must match.
        9. Symbol: valid uppercase non-empty string.
        """
        errors: List[str] = []

        # Extract fields from dict or EODQuote
        if isinstance(record, EODQuote):
            symbol = record.symbol
            trade_date = record.trade_date
            raw_open = record.open_price
            raw_high = record.high_price
            raw_low = record.low_price
            raw_close = record.close_price
            raw_volume = record.volume
            raw_value = record.value
        elif isinstance(record, dict):
            symbol = record.get("symbol")
            trade_date = record.get("trade_date")
            raw_open = record.get("open_price")
            raw_high = record.get("high_price")
            raw_low = record.get("low_price")
            raw_close = record.get("close_price")
            raw_volume = record.get("volume")
            raw_value = record.get("value")
        else:
            return False, ["Record must be an EODQuote or a dictionary"]

        # 1. Symbol validation (if provided)
        if symbol is not None:
            sym_str = str(symbol).strip().upper()
            if not sym_str or not re.match(r"^[A-Z0-9_\-\.]{1,20}$", sym_str):
                errors.append(f"Invalid symbol format: '{symbol}'")

        # 2. Trade date validation (if provided)
        if trade_date is not None:
            if isinstance(trade_date, str):
                try:
                    trade_date = date.fromisoformat(trade_date)
                except ValueError:
                    errors.append(f"Invalid trade_date format: '{trade_date}'")
            if isinstance(trade_date, date):
                if target_date is not None and trade_date != target_date:
                    errors.append(
                        f"Trade date '{trade_date}' does not match expected target date '{target_date}'"
                    )
                if trade_date > date.today():
                    errors.append(f"Trade date '{trade_date}' is in the future")

        # 3. Numeric conversions & sanity
        open_d = cls._to_decimal(raw_open)
        high_d = cls._to_decimal(raw_high)
        low_d = cls._to_decimal(raw_low)
        close_d = cls._to_decimal(raw_close)

        if None in (open_d, high_d, low_d, close_d):
            errors.append("All OHLC prices must be valid, finite numeric values (NaN and Inf are prohibited)")
        else:
            if open_d <= 0 or high_d <= 0 or low_d <= 0 or close_d <= 0:
                errors.append("All OHLC prices must be strictly positive (> 0)")
            if high_d < open_d or high_d < close_d or high_d < low_d:
                errors.append(
                    f"High price ({high_d}) is lower than Open ({open_d}), Close ({close_d}), or Low ({low_d})"
                )
            if low_d > open_d or low_d > close_d or low_d > high_d:
                errors.append(
                    f"Low price ({low_d}) is higher than Open ({open_d}), Close ({close_d}), or High ({high_d})"
                )

        # 4. Volume check
        if raw_volume is None or not cls._is_finite_number(raw_volume):
            errors.append("Volume must be a valid, finite non-negative number")
        else:
            try:
                vol_d = Decimal(str(raw_volume))
                if vol_d < 0:
                    errors.append(f"Volume must be non-negative (received {vol_d})")
            except (ValueError, TypeError, InvalidOperation):
                errors.append("Volume could not be parsed as a numeric value")

        # 5. Value check (if present)
        if raw_value is not None:
            val_d = cls._to_decimal(raw_value)
            if val_d is None:
                errors.append("Turnover value must be a valid finite number if provided")
            elif val_d < 0:
                errors.append(f"Turnover value must be non-negative (received {val_d})")

        is_valid = len(errors) == 0
        return is_valid, errors

    def validate_dataset(
        self,
        records: List[Union[Dict[str, Any], EODQuote]],
        target_date: Optional[date] = None,
    ) -> Tuple[List[Any], List[Dict[str, Any]]]:
        """Validate a collection of quotes, enforcing intra-batch deduplication."""
        valid: List[Any] = []
        invalid: List[Dict[str, Any]] = []
        seen_keys: Set[Tuple[str, Optional[date]]] = set()

        for record in records:
            # Extract key for deduplication
            if isinstance(record, EODQuote):
                sym = record.symbol.strip().upper()
                dt = record.trade_date
                record_dict = record.model_dump()
            else:
                sym = str(record.get("symbol", "")).strip().upper()
                dt = record.get("trade_date")
                if isinstance(dt, str):
                    try:
                        dt = date.fromisoformat(dt)
                    except ValueError:
                        pass
                record_dict = dict(record)

            is_valid, errs = self.validate_ohlc_record(record, target_date=target_date)

            # Intra-batch duplicate check
            if sym and dt:
                batch_key = (sym, dt)
                if batch_key in seen_keys:
                    is_valid = False
                    errs.append(f"Duplicate quote record for symbol '{sym}' on date '{dt}' in batch")
                else:
                    seen_keys.add(batch_key)

            if is_valid:
                valid.append(record)
            else:
                record_dict["validation_errors"] = errs
                invalid.append(record_dict)

        logger.info(
            "Validation complete: %d valid, %d invalid/rejected",
            len(valid),
            len(invalid),
        )
        return valid, invalid
