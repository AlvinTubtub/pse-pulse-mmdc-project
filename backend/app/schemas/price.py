"""Daily price Pydantic schemas."""

from datetime import date
from decimal import Decimal
from typing import Optional
from backend.app.schemas.common import BaseSchema


class DailyPriceRead(BaseSchema):
    id: int
    company_id: int
    trade_date: date
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: Decimal
    value: Optional[float] = None
