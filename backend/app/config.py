"""Centralized configuration management for PSE Pulse.

Uses pydantic-settings for robust environment variable validation and defaults.
"""

from functools import lru_cache
import json
from typing import List, Union
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core Application Settings
    PROJECT_NAME: str = "PSE Pulse — Personal Azure Edition"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", description="development, staging, or production")
    DEBUG: bool = Field(default=False, description="Enable debug mode (never enable in production)")
    LOG_LEVEL: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")

    # Network Binding
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_V1_PREFIX: str = "/api/v1"

    # Database
    # Default to local SQLite for fast self-contained local runs/testing;
    # overridden by DATABASE_URL (e.g. postgresql+psycopg://...) in production or compose.
    DATABASE_URL: str = Field(
        default="sqlite:///./pse_pulse_dev.db",
        description="Database connection URL. Supports PostgreSQL (psycopg) and SQLite.",
    )

    # CORS
    # In production, this should be restricted to the exact origin(s).
    # Supports comma-separated strings (e.g. "http://a,http://b"), JSON arrays, or native lists.
    CORS_ORIGINS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    @field_validator("CORS_ORIGINS")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins from comma-separated string, JSON array, or list."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return v

    # Development & Demo Controls
    DEMO_MODE: bool = Field(
        default=True,
        description="When true, clearly marks generated or seeded data as demo/development data.",
    )
    AUTO_CREATE_SCHEMA: bool = Field(
        default=False,
        description="Whether to run Base.metadata.create_all() at startup. Defaults to False (Alembic is authoritative). Never allow in production.",
    )

    @model_validator(mode="after")
    def validate_production_guards(self) -> "Settings":
        """Fail fast if synthetic demo mode or auto schema creation is enabled in production."""
        if self.ENVIRONMENT.lower() == "production":
            if self.DEMO_MODE:
                raise ValueError(
                    "DEMO_MODE must be false when ENVIRONMENT=production. "
                    "Synthetic market data cannot be enabled in production."
                )
            if self.AUTO_CREATE_SCHEMA:
                raise ValueError(
                    "AUTO_CREATE_SCHEMA must be false when ENVIRONMENT=production. "
                    "Production schema must be managed exclusively through Alembic."
                )
        return self

    # Real ML Model & Forecasting Controls
    REAL_MODELS_ENABLED: bool = Field(
        default=False,
        description="Gate controlling activation of real model training and inference pipelines in production.",
    )
    MODEL_ARTIFACT_ACTIVATION_ENABLED: bool = Field(
        default=False,
        description="Separate safety gate permitting explicit ModelArtifact activation operations.",
    )
    MODEL_ARTIFACTS_DIR: str = Field(
        default="backend/artifacts/models",
        description="Directory for versioned production model artifacts.",
    )

    # Azure Blob Storage Scaffolding (Optional / Scaffolding only)
    AZURE_STORAGE_CONNECTION_STRING: str | None = None
    AZURE_STORAGE_CONTAINER_NAME: str = "pse-pulse-data"



@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
