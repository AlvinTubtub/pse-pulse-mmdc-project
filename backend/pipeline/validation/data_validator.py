"""Data validation rules for PSE Pulse market data."""

from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class DataValidator:
    """Validates raw price feeds against financial sanity constraints."""

    @staticmethod
    def validate_ohlc_record(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a single OHLC record.

        Rules:
        1. Open, High, Low, Close must be positive numbers.
        2. High must be >= Open, Close, and Low.
        3. Low must be <= Open, Close, and High.
        4. Volume must be >= 0.
        """
        errors: List[str] = []
        try:
            open_p = float(record.get("open_price", 0))
            high_p = float(record.get("high_price", 0))
            low_p = float(record.get("low_price", 0))
            close_p = float(record.get("close_price", 0))
            volume = int(record.get("volume", 0))

            if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
                errors.append("All OHLC prices must be strictly positive")
            if high_p < open_p or high_p < close_p or high_p < low_p:
                errors.append(f"High price ({high_p}) is lower than Open ({open_p}), Close ({close_p}), or Low ({low_p})")
            if low_p > open_p or low_p > close_p or low_p > high_p:
                errors.append(f"Low price ({low_p}) is higher than Open ({open_p}), Close ({close_p}), or High ({high_p})")
            if volume < 0:
                errors.append("Volume must be non-negative")
        except (ValueError, TypeError) as e:
            errors.append(f"Invalid numeric format: {str(e)}")

        is_valid = len(errors) == 0
        return is_valid, errors

    def validate_dataset(self, records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Split records into valid and rejected sets."""
        valid: List[Dict[str, Any]] = []
        invalid: List[Dict[str, Any]] = []

        for record in records:
            ok, errs = self.validate_ohlc_record(record)
            if ok:
                valid.append(record)
            else:
                record_copy = dict(record)
                record_copy["validation_errors"] = errs
                invalid.append(record_copy)

        logger.info("Validation complete: %d valid, %d invalid", len(valid), len(invalid))
        return valid, invalid
