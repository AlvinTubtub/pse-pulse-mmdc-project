"""Database history adapter converting DailyPrice rows into real OhlcvRecord domain objects."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
import logging
import math

from sqlalchemy.orm import Session

from backend.app.forecasting.real.domain import OhlcvRecord, require_chronological_records
from backend.app.models.company import Company
from backend.app.models.price import DailyPrice

logger = logging.getLogger(__name__)


def load_company_ohlcv_history(
    db: Session,
    symbol_or_id: str | int,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[OhlcvRecord, ...]:
    """Query DailyPrice records for a company, strictly ordered by trade_date ASC.

    Preserves exact Decimal/Numeric values in PostgreSQL/SQLite until this model boundary,
    where values are converted to validated finite float64.
    """
    if isinstance(symbol_or_id, int):
        company = db.query(Company).filter(Company.id == symbol_or_id).first()
    else:
        company = db.query(Company).filter(Company.symbol == str(symbol_or_id)).first()

    if not company:
        raise ValueError(f"Company '{symbol_or_id}' not found in database")
    symbol = company.symbol

    query = (
        db.query(DailyPrice)
        .filter(DailyPrice.company_id == company.id)
        .order_by(DailyPrice.trade_date.asc())
    )
    if start_date is not None:
        query = query.filter(DailyPrice.trade_date >= start_date)
    if end_date is not None:
        query = query.filter(DailyPrice.trade_date <= end_date)

    rows = query.all()
    if not rows:
        raise ValueError(f"No historical DailyPrice observations found for {symbol}")

    records: list[OhlcvRecord] = []
    for row in rows:
        # Convert exact Decimal to float64 with finiteness and positivity verification
        try:
            o_val = float(Decimal(str(row.open_price)))
            h_val = float(Decimal(str(row.high_price)))
            l_val = float(Decimal(str(row.low_price)))
            c_val = float(Decimal(str(row.close_price)))
            v_val = float(Decimal(str(row.volume)))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Failed to convert price values for {symbol} on {row.trade_date}: {exc}"
            ) from exc

        record = OhlcvRecord(
            trading_date=row.trade_date,
            open=o_val,
            high=h_val,
            low=l_val,
            close=c_val,
            volume=v_val,
        )
        records.append(record)

    record_tuple = tuple(records)
    require_chronological_records(record_tuple)
    logger.debug(
        "Loaded OHLCV history for %s: count=%d, start=%s, end=%s",
        symbol,
        len(record_tuple),
        record_tuple[0].trading_date,
        record_tuple[-1].trading_date,
    )
    return record_tuple
