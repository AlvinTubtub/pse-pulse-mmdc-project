"""Offline startup guard for the production API process."""

import sys

from backend.app.config import get_settings
from backend.app.runtime_policy import validate_api_listener


def validate_api_process() -> None:
    settings = get_settings()
    if settings.ENVIRONMENT.lower() != "production":
        raise RuntimeError("Production API requires ENVIRONMENT=production.")
    if settings.DEBUG or settings.DEMO_MODE or settings.AUTO_CREATE_SCHEMA:
        raise RuntimeError("Unsafe production mode flags are enabled.")
    if settings.REAL_MODELS_ENABLED or settings.MODEL_ARTIFACT_ACTIVATION_ENABLED:
        raise RuntimeError("API inference and model activation must remain disabled.")
    if settings.PROCESS_ROLE != "api":
        raise RuntimeError("The API unit requires PROCESS_ROLE=api.")
    validate_api_listener(settings.HOST, settings.PORT)
    if not settings.DATABASE_URL or not settings.EXPECTED_PRIVATE_DATABASE_HOST:
        raise RuntimeError("Production API database configuration is incomplete.")


def main() -> int:
    try:
        validate_api_process()
    except Exception:
        print("Production process configuration rejected; diagnostics are restricted to service logs.", file=sys.stderr)
        return 1
    print("Production API configuration accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
