"""Forecast and Model Pydantic schemas."""

from datetime import date, datetime
from typing import Optional, List
from backend.app.schemas.common import BaseSchema


class ModelMetadataRead(BaseSchema):
    id: int
    name: str
    code: str
    version: str
    description: Optional[str] = None
    is_active: bool


class ForecastRead(BaseSchema):
    id: int
    company_id: int
    symbol: Optional[str] = None
    model_id: int
    model_name: Optional[str] = None
    model_code: Optional[str] = None
    target_date: date
    predicted_price: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    confidence_level: float
    is_demo: bool
    pipeline_run_id: Optional[int] = None
    created_at: datetime


class LatestForecastsResponse(BaseSchema):
    is_demo: bool = True
    disclaimer: str = (
        "DEMO DATA: Forecasts are generated using lightweight baseline stubs for development and architectural verification only. "
        "Not financial advice. Not real market predictions."
    )
    generated_at: datetime
    forecasts: List[ForecastRead]
