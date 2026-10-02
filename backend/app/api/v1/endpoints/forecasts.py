"""Forecast endpoints for PSE Pulse."""

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from backend.app.database import get_db
from backend.app.models.forecast import Forecast
from backend.app.models.company import Company
from backend.app.models.model_metadata import ModelMetadata
from backend.app.schemas.forecast import (
    LatestForecastsResponse,
    ForecastRead,
)

router = APIRouter()


@router.get("/latest", response_model=LatestForecastsResponse)
def get_latest_forecasts(
    symbol: Optional[str] = Query(None, description="Filter by company symbol (e.g. SMPH)"),
    model_code: Optional[str] = Query(None, description="Filter by model code (e.g. LAG_REGRESSION, ARIMA, LSTM)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum forecast points to return"),
    db: Session = Depends(get_db),
):
    """Retrieve latest forward forecasts across supported models.

    All returned predictions are explicitly marked as demo/development data.
    """
    query = (
        db.query(Forecast)
        .options(
            joinedload(Forecast.company),
            joinedload(Forecast.model_metadata),
        )
    )

    if symbol:
        clean_symbol = symbol.strip().upper()
        query = query.join(Company).filter(Company.symbol == clean_symbol)

    if model_code:
        clean_code = model_code.strip().upper()
        query = query.join(ModelMetadata).filter(ModelMetadata.code == clean_code)

    forecast_records = (
        query.order_by(Forecast.target_date.asc(), Forecast.id.desc())
        .limit(limit)
        .all()
    )

    items = [
        ForecastRead(
            id=f.id,
            company_id=f.company_id,
            symbol=f.company.symbol if f.company else None,
            model_id=f.model_id,
            model_name=f.model_metadata.name if f.model_metadata else None,
            model_code=f.model_metadata.code if f.model_metadata else None,
            target_date=f.target_date,
            predicted_price=float(f.predicted_price),
            lower_bound=float(f.lower_bound) if f.lower_bound is not None else None,
            upper_bound=float(f.upper_bound) if f.upper_bound is not None else None,
            confidence_level=f.confidence_level,
            is_demo=f.is_demo,
            pipeline_run_id=f.pipeline_run_id,
            created_at=f.created_at,
        )
        for f in forecast_records
    ]

    return LatestForecastsResponse(
        is_demo=True,
        disclaimer=(
            "DEMO DATA: Predictions are generated using lightweight architectural baseline stubs "
            "for development, layout testing, and API verification. Not financial advice."
        ),
        generated_at=datetime.now(timezone.utc),
        forecasts=items,
    )
