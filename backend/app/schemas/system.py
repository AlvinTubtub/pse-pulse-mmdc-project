"""System status and health schemas."""

from typing import Dict, Any, Optional
from backend.app.schemas.common import BaseSchema


class SystemStatusResponse(BaseSchema):
    status: str
    environment: str
    debug: bool
    version: str
    database: Dict[str, Any]
    memory: Optional[Dict[str, Any]] = None
    demo_mode: bool
    deployment_target: Dict[str, str] = {
        "cloud": "Azure for Students",
        "primary_vm_sku": "Standard_B2ats_v2 (2 vCPU, 1 GiB RAM)",
        "fallback_vm_sku": "Standard_B1s (1 vCPU, 1 GiB RAM)",
        "database_sku": "Azure Database for PostgreSQL Flexible Server (Burstable B1ms, 32GB)",
        "blob_tier": "Standard LRS Hot (< 5GB)",
    }
