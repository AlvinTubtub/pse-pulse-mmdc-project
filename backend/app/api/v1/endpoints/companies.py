"""Company endpoints for PSE Pulse."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from backend.app.database import get_db
from backend.app.models.company import Company
from backend.app.models.sector import Sector
from backend.app.models.price import DailyPrice
from backend.app.schemas.company import (
    CompanySummary,
    CompanyDetail,
    CompanyRead,
)
from backend.app.schemas.price import DailyPriceRead

router = APIRouter()


@router.get("", response_model=List[CompanySummary])
def list_companies(
    sector: Optional[str] = Query(None, description="Filter by sector code or name"),
    db: Session = Depends(get_db),
):
    """Retrieve list of listed companies with latest summary market data."""
    query = db.query(Company).options(joinedload(Company.sector)).filter(Company.is_active == True)

    if sector:
        query = query.join(Sector).filter(
            (Sector.code.ilike(sector)) | (Sector.name.ilike(f"%{sector}%"))
        )

    companies = query.order_by(Company.symbol.asc()).all()

    summaries: List[CompanySummary] = []
    for c in companies:
        # Fetch latest 2 prices to compute change
        latest_prices = (
            db.query(DailyPrice)
            .filter(DailyPrice.company_id == c.id)
            .order_by(DailyPrice.trade_date.desc())
            .limit(2)
            .all()
        )

        latest_close = None
        change_pct = None
        trade_date = None

        if latest_prices:
            latest_close = float(latest_prices[0].close_price)
            trade_date = latest_prices[0].trade_date
            if len(latest_prices) > 1:
                prev_close = float(latest_prices[1].close_price)
                if prev_close > 0:
                    change_pct = round(((latest_close - prev_close) / prev_close) * 100, 2)

        summaries.append(
            CompanySummary(
                id=c.id,
                symbol=c.symbol,
                name=c.name,
                sector_name=c.sector.name if c.sector else "Unknown",
                latest_close=latest_close,
                change_pct=change_pct,
                trade_date=trade_date,
            )
        )

    return summaries


@router.get("/{symbol}", response_model=CompanyDetail)
def get_company(
    symbol: str,
    db: Session = Depends(get_db),
):
    """Retrieve single company details and recent historical daily prices."""
    clean_symbol = symbol.strip().upper()
    company = (
        db.query(Company)
        .options(joinedload(Company.sector))
        .filter(Company.symbol == clean_symbol)
        .first()
    )

    if not company:
        raise HTTPException(
            status_code=404,
            detail=f"Company with symbol '{clean_symbol}' not found.",
        )

    # Get past 20 trading days of prices
    prices = (
        db.query(DailyPrice)
        .filter(DailyPrice.company_id == company.id)
        .order_by(DailyPrice.trade_date.desc())
        .limit(20)
        .all()
    )

    recent_prices = [
        DailyPriceRead(
            id=p.id,
            company_id=p.company_id,
            trade_date=p.trade_date,
            open_price=float(p.open_price),
            high_price=float(p.high_price),
            low_price=float(p.low_price),
            close_price=float(p.close_price),
            volume=p.volume,
            value=float(p.value) if p.value is not None else None,
        )
        for p in prices
    ]

    return CompanyDetail(
        id=company.id,
        symbol=company.symbol,
        name=company.name,
        sector_id=company.sector_id,
        is_active=company.is_active,
        listing_date=company.listing_date,
        created_at=company.created_at,
        updated_at=company.updated_at,
        sector=company.sector,
        recent_prices=recent_prices,
    )
