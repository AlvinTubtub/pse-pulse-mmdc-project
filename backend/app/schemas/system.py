"""Public health/readiness response models with no infrastructure details."""

from backend.app.schemas.common import BaseSchema


class SystemStatusResponse(BaseSchema):
    status: str
    environment: str
    debug: bool
    version: str
    database: str
    demo_mode: bool
