"""Dependency readiness without public infrastructure or exception details."""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.config import get_settings, Settings
from backend.app.database import get_db
from backend.app.schemas.system import SystemStatusResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status", response_model=SystemStatusResponse)
def get_system_status(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    """Return a generic status for the UI; diagnostics stay in restricted logs."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness database probe failed.")
        return SystemStatusResponse(
            status="degraded",
            environment=settings.ENVIRONMENT,
            debug=settings.DEBUG,
            version=settings.VERSION,
            database="unavailable",
            demo_mode=settings.DEMO_MODE,
        )
    return SystemStatusResponse(
        status="operational",
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
        version=settings.VERSION,
        database="connected",
        demo_mode=settings.DEMO_MODE,
    )
