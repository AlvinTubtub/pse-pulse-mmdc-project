"""Production settings negative tests. No live database is contacted."""

import pytest
from backend.app.config import Settings


def _valid_production_values(ca_file):
    host = "owner-verified.private.postgres.database.azure.com"
    return {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "DEMO_MODE": False,
        "AUTO_CREATE_SCHEMA": False,
        "REAL_MODELS_ENABLED": False,
        "MODEL_ARTIFACT_ACTIVATION_ENABLED": False,
        "PROCESS_ROLE": "api",
        "HOST": "127.0.0.1",
        "PORT": 8000,
        "EXPECTED_PRIVATE_DATABASE_HOST": host,
        "DATABASE_TLS_ROOT_CERT": str(ca_file),
        "DATABASE_URL": f"postgresql+psycopg://unit:REDACTED@{host}:5432/test?sslmode=verify-full&sslrootcert={ca_file}",
    }


def test_valid_production_configuration_uses_verified_private_postgres(tmp_path):
    ca = tmp_path / "root.pem"
    ca.write_text("offline test CA")
    settings = Settings(**_valid_production_values(ca))
    assert settings.ENVIRONMENT == "production"
    assert settings.DEMO_MODE is False
    assert settings.REAL_MODELS_ENABLED is False


@pytest.mark.parametrize(
    "override",
    [
        {"DEBUG": True},
        {"DEMO_MODE": True},
        {"AUTO_CREATE_SCHEMA": True},
        {"REAL_MODELS_ENABLED": True},
        {"MODEL_ARTIFACT_ACTIVATION_ENABLED": True},
        {"HOST": "0.0.0.0"},
        {"PORT": 8001},
        {"DATABASE_URL": "sqlite:///prod.db"},
        {"DATABASE_URL": "postgresql+psycopg://unit:REDACTED@public.postgres.database.azure.com:5432/test?sslmode=verify-full&sslrootcert=/tmp/root.pem"},
        {"DATABASE_URL": "postgresql+psycopg://unit:REDACTED@owner-verified.private.postgres.database.azure.com:5432/test?sslmode=require&sslrootcert=/tmp/root.pem"},
    ],
)
def test_unsafe_production_settings_reject(tmp_path, override):
    ca = tmp_path / "root.pem"
    ca.write_text("offline test CA")
    values = _valid_production_values(ca)
    values.update(override)
    with pytest.raises(ValueError):
        Settings(**values)
