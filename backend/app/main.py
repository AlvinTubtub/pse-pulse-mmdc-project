"""PSE Pulse — Personal Azure Edition
FastAPI Backend Application Entrypoint.

Architectured for minimal memory footprint (~1 GiB RAM host VM),
static Next.js frontend delivery via Nginx, and Azure Database for PostgreSQL.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.config import get_settings
from backend.app.database import engine, Base, SessionLocal
from backend.app.services.seed_data import seed_database_if_empty
from backend.app.api.v1.router import api_router
from backend.app.schemas.common import HealthResponse

# Logging configuration
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("pse_pulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database tables and seed baseline data."""
    is_production = settings.ENVIRONMENT.lower() == "production"

    if is_production:
        logger.info("Production environment detected.")
        logger.info("Automatic schema creation disabled.")
        logger.info("Demo database seeding disabled.")
        logger.info("Schema must be managed through Alembic.")
    else:
        logger.info("Non-production environment (%s): initializing schema via create_all...", settings.ENVIRONMENT)
        Base.metadata.create_all(bind=engine)

        if settings.DEMO_MODE:
            logger.info("DEMO_MODE is True: seeding baseline demo data if database is empty...")
            db = SessionLocal()
            try:
                seed_database_if_empty(db)
            except Exception as e:
                logger.error("Error during initial data seed: %s", e)
            finally:
                db.close()
        else:
            logger.info("DEMO_MODE is False: skipping demo data seeding.")

    logger.info("Application startup complete. Environment: %s", settings.ENVIRONMENT)
    yield
    logger.info("Application shutting down...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Personal PSE market analytics and forecasting engine, optimized for "
        "Azure for Students free-tier deployment (B2ats_v2 VM + PostgreSQL B1ms)."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception processing %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact the administrator."},
    )


# Root Health Check for monitoring, Nginx upstream checks, and systemd
@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """Small lightweight health probe endpoint."""
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/", tags=["Root"])
def root():
    """Root metadata response."""
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "api_v1": settings.API_V1_PREFIX,
    }


# Mount versioned API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
