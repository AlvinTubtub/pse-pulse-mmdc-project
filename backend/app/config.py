"""Centralized configuration management for PSE Pulse.

Uses pydantic-settings for robust environment variable validation and defaults.
"""

from functools import lru_cache
import json
from pathlib import Path
from typing import List, Union
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from backend.app.runtime_policy import (
    validate_database_url,
    validate_production_flags,
    validate_api_listener,
    verify_private_database_resolution as _verify_private_database_resolution,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
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
    EXPECTED_PRIVATE_DATABASE_HOST: str | None = Field(
        default=None,
        description="Owner-verified PostgreSQL FQDN, copied from the existing Azure resource output.",
    )
    DATABASE_TLS_ROOT_CERT: str = "/etc/ssl/certs/ca-certificates.crt"
    PROCESS_ROLE: str = "api"

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

    # Production model gates and artifact location.
    REAL_MODELS_ENABLED: bool = Field(
        default=False,
        description="Gate controlling real production inference.",
    )
    MODEL_ARTIFACT_ACTIVATION_ENABLED: bool = Field(
        default=False,
        description="Separate safety gate permitting explicit ModelArtifact activation operations.",
    )
    MODEL_ARTIFACTS_DIR: str = Field(
        default="backend/artifacts/models",
        description="Directory for versioned production model artifacts.",
    )
    AZURE_STORAGE_CONNECTION_STRING: str | None = None
    AZURE_STORAGE_CONTAINER_NAME: str = "pse-pulse-data"

    @model_validator(mode="after")
    def validate_production_guards(self) -> "Settings":
        """Fail fast on unsafe or ambiguous production configuration."""
        if self.ENVIRONMENT.lower() == "production":
            validate_production_flags(
                environment=self.ENVIRONMENT,
                debug=self.DEBUG,
                demo_mode=self.DEMO_MODE,
                auto_create_schema=self.AUTO_CREATE_SCHEMA,
                real_models_enabled=self.REAL_MODELS_ENABLED,
                activation_enabled=self.MODEL_ARTIFACT_ACTIVATION_ENABLED,
                process_role=self.PROCESS_ROLE,
            )
            if self.PROCESS_ROLE != "production-eod" and self.REAL_MODELS_ENABLED:
                raise ValueError("REAL_MODELS_ENABLED may only be true in the dedicated production EOD process.")
            if self.PROCESS_ROLE == "api":
                validate_api_listener(self.HOST, self.PORT)
            validate_database_url(
                self.DATABASE_URL,
                self.EXPECTED_PRIVATE_DATABASE_HOST,
                self.DATABASE_TLS_ROOT_CERT,
            )
        return self


def verify_private_database_resolution(host: str) -> set[str]:
    """Refuse database connections if the owner-verified name resolves publicly."""
    return _verify_private_database_resolution(host)


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
