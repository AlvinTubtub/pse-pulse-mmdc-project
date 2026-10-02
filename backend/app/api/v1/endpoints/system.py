"""System status endpoints."""

from datetime import datetime, timezone
import os
import resource
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.config import get_settings, Settings
from backend.app.database import get_db
from backend.app.schemas.system import SystemStatusResponse

router = APIRouter()


@router.get("/status", response_model=SystemStatusResponse)
def get_system_status(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    """Retrieve detailed operational system health and resource metrics."""
    # Check DB connectivity
    db_status = "connected"
    db_type = "sqlite" if settings.DATABASE_URL.startswith("sqlite") else "postgresql"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    # Measure current process memory (RSS) using standard library resource module
    # On macOS ru_maxrss is in bytes; on Linux ru_maxrss is in kilobytes.
    rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = round(rss_raw / (1024 * 1024) if "darwin" in os.sys.platform else rss_raw / 1024, 2)

    return SystemStatusResponse(
        status="operational" if db_status == "connected" else "degraded",
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
        version=settings.VERSION,
        database={
            "status": db_status,
            "engine": db_type,
        },
        memory={
            "process_rss_mb": rss_mb,
            "target_host_ram_mb": 1024,
            "estimated_footprint_pct": round((rss_mb / 1024) * 100, 2),
        },
        demo_mode=settings.DEMO_MODE,
    )
