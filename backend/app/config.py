"""Centralized configuration management for PSE Pulse.

Uses pydantic-settings for robust environment variable validation and defaults.
"""

from functools import lru_cache
from typing import List
from pydantic import Field
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
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    # Development & Demo Controls
    DEMO_MODE: bool = Field(
        default=True,
        description="When true, clearly marks generated or seeded data as demo/development data.",
    )

    # Azure Blob Storage Scaffolding (Optional / Scaffolding only)
    AZURE_STORAGE_CONNECTION_STRING: str | None = None
    AZURE_STORAGE_CONTAINER_NAME: str = "pse-pulse-data"


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
