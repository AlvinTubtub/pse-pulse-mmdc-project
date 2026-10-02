"""Company Pydantic schemas."""

from datetime import date, datetime
from typing import Optional, List
from backend.app.schemas.common import BaseSchema
from backend.app.schemas.sector import SectorRead
from backend.app.schemas.price import DailyPriceRead


class CompanyBase(BaseSchema):
    symbol: str
    name: str
    sector_id: int
    is_active: bool = True
    listing_date: Optional[date] = None


class CompanyRead(CompanyBase):
    id: int
    created_at: datetime
    updated_at: datetime
    sector: Optional[SectorRead] = None


class CompanySummary(BaseSchema):
    id: int
    symbol: str
    name: str
    sector_name: str
    latest_close: Optional[float] = None
    change_pct: Optional[float] = None
    trade_date: Optional[date] = None


class CompanyDetail(CompanyRead):
    recent_prices: List[DailyPriceRead] = []
