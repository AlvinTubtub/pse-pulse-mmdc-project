"""Tests for centralized configuration and lifespan startup safety."""

from unittest.mock import patch, MagicMock
import pytest
from backend.app.config import Settings
from backend.app.main import lifespan, app


def test_settings_defaults():
    s = Settings()
    assert s.PROJECT_NAME == "PSE Pulse — Personal Azure Edition"
    assert s.API_V1_PREFIX == "/api/v1"
    assert s.DEMO_MODE is True
    assert s.DEBUG is False
    assert len(s.CORS_ORIGINS) >= 2


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("DEMO_MODE", "false")
    s = Settings()
    assert s.ENVIRONMENT == "production"
    assert s.DEBUG is False
    assert s.DEMO_MODE is False


def test_settings_production_demo_mode_rejected(monkeypatch):
    """Production with DEMO_MODE=true must fail configuration validation fast."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEMO_MODE", "true")
    with pytest.raises(ValueError, match="DEMO_MODE must be false when ENVIRONMENT=production"):
        Settings()


def test_settings_production_demo_mode_false_valid(monkeypatch):
    """Production with DEMO_MODE=false is valid."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEMO_MODE", "false")
    s = Settings()
    assert s.ENVIRONMENT == "production"
    assert s.DEMO_MODE is False


def test_settings_development_demo_mode_true_valid(monkeypatch):
    """Development with DEMO_MODE=true is valid."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DEMO_MODE", "true")
    s = Settings()
    assert s.ENVIRONMENT == "development"
    assert s.DEMO_MODE is True


def test_settings_development_demo_mode_false_valid(monkeypatch):
    """Development with DEMO_MODE=false is valid."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DEMO_MODE", "false")
    s = Settings()
    assert s.ENVIRONMENT == "development"
    assert s.DEMO_MODE is False


def test_settings_cors_comma_separated_env(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://pse-pulse.eastus.cloudapp.azure.com,https://api.psepulse.com",
    )
    s = Settings()
    assert s.CORS_ORIGINS == [
        "https://pse-pulse.eastus.cloudapp.azure.com",
        "https://api.psepulse.com",
    ]
    assert len(s.CORS_ORIGINS) == 2


def test_settings_cors_json_array_env(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        '["http://alpha.internal:3000", "http://beta.internal:3000"]',
    )
    s = Settings()
    assert s.CORS_ORIGINS == [
        "http://alpha.internal:3000",
        "http://beta.internal:3000",
    ]


def test_settings_cors_empty_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    s = Settings()
    assert s.CORS_ORIGINS == []


@pytest.mark.asyncio
async def test_lifespan_production_guards_create_all_and_seed(monkeypatch):
    """In production with DEMO_MODE=false, lifespan must not create tables or seed demo records."""
    monkeypatch.setattr("backend.app.main.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.app.main.settings.DEMO_MODE", False)

    with patch("backend.app.main.Base.metadata.create_all") as mock_create_all, \
         patch("backend.app.main.seed_database_if_empty") as mock_seed:
        async with lifespan(app):
            pass

        mock_create_all.assert_not_called()
        mock_seed.assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_production_never_seeds_even_if_demo_mode_true(monkeypatch):
    """Defense-in-depth: Even if DEMO_MODE were true in production, lifespan must never seed."""
    monkeypatch.setattr("backend.app.main.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.app.main.settings.DEMO_MODE", True)

    with patch("backend.app.main.Base.metadata.create_all") as mock_create_all, \
         patch("backend.app.main.seed_database_if_empty") as mock_seed:
        async with lifespan(app):
            pass

        mock_create_all.assert_not_called()
        mock_seed.assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_development_invokes_create_all_and_seed(monkeypatch):
    """In non-production development with DEMO_MODE=true, lifespan initializes schema and seeds data."""
    monkeypatch.setattr("backend.app.main.settings.ENVIRONMENT", "development")
    monkeypatch.setattr("backend.app.main.settings.DEMO_MODE", True)

    with patch("backend.app.main.Base.metadata.create_all") as mock_create_all, \
         patch("backend.app.main.seed_database_if_empty") as mock_seed:
        async with lifespan(app):
            pass

        mock_create_all.assert_called_once()
        mock_seed.assert_called_once()
