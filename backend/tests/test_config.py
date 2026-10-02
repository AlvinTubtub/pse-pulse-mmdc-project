"""Tests for centralized configuration."""

from backend.app.config import Settings


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
