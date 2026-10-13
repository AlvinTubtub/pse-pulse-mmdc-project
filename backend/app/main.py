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
from sqlalchemy import inspect, text

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


def _database_schema_ready_for_seed() -> bool:
    """Return whether the migrated schema has the table required for seeding."""
    return inspect(engine).has_table("sectors")


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
        if settings.AUTO_CREATE_SCHEMA:
            logger.info("Non-production environment (%s): initializing schema via create_all...", settings.ENVIRONMENT)
            Base.metadata.create_all(bind=engine)
        else:
            logger.info("Non-production environment (%s): Alembic is authoritative for schema. Automatic create_all disabled.", settings.ENVIRONMENT)

        if settings.DEMO_MODE:
            logger.info("DEMO_MODE is True: checking if database requires baseline seeding...")
            if _database_schema_ready_for_seed():
                db = SessionLocal()
                try:
                    seed_database_if_empty(db)
                except Exception as e:
                    logger.exception("Non-production database seed failed.")
                finally:
                    db.close()
            else:
                logger.info("Database schema not yet migrated (run 'alembic upgrade head'). Skipping seeding.")
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
        "a private PostgreSQL deployment with a same-origin HTTPS reverse proxy."
    ),
    lifespan=lifespan,
    docs_url=None if settings.ENVIRONMENT.lower() == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT.lower() == "production" else "/redoc",
    openapi_url=None if settings.ENVIRONMENT.lower() == "production" else "/openapi.json",
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
    logger.exception("Unhandled request failure: method=%s path=%s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact the administrator."},
    )


# Liveness never checks PostgreSQL, so a dependency outage does not restart the API.
@app.get("/health/live", response_model=HealthResponse, tags=["Health"])
@app.get("/health", response_model=HealthResponse, tags=["Health"], include_in_schema=False)
def liveness_check():
    """Confirm that the process can answer an HTTP request."""
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health/ready", tags=["Health"])
def readiness_check():
    """Check required DB readiness without exposing driver errors."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness probe could not reach its database dependency.")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "reason": "dependency_unavailable"},
        )
    return {"status": "ready"}


@app.get("/", tags=["Root"])
def root():
    """Root metadata response."""
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "api_v1": settings.API_V1_PREFIX,
    }


# Mount versioned API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
