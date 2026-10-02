"""API v1 Router aggregation."""

from fastapi import APIRouter
from backend.app.api.v1.endpoints import (
    system,
    companies,
    forecasts,
    pipeline,
    models,
)

api_router = APIRouter()

api_router.include_router(system.router, prefix="/system", tags=["System"])
api_router.include_router(companies.router, prefix="/companies", tags=["Companies"])
api_router.include_router(forecasts.router, prefix="/forecasts", tags=["Forecasts"])
api_router.include_router(pipeline.router, prefix="/pipeline", tags=["Pipeline"])
api_router.include_router(models.router, prefix="/models", tags=["Models"])
